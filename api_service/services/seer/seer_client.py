import aiohttp
import asyncio
from typing import List, Set
from api_service.services.http.base_client import BaseHTTPClient
from api_service.config.logger_manager import LoggerManager
from api_service.db.database_manager import DatabaseManager
from api_service.services.request_sources import is_tmdb_metadata_source_id
from api_service.utils.tmdb_images import tmdb_image_url

BATCH_SIZE = 20  # Number of requests fetched per batch
HTTP_OK = {200, 201, 202}  # Include 202 Accepted for async operations
from api_service.services.seer.seer_status import (
    AVAILABLE_MEDIA_STATUSES,
    derive_seer_status,
)


def _as_bool(value):
    """Normalize bool-like config values."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


class SeerClient(BaseHTTPClient):
    """
    A client to interact with the Seer service API for handling media requests and authentication.
    """
    
    # Override HTTP_OK to include 202 Accepted for async operations
    HTTP_OK = {200, 201, 202}

    def __init__(self, api_url, api_key, seer_user_name=None, seer_password=None, session_token=None,
                number_of_seasons="all", exclude_downloaded=True, exclude_watched=True,
                anime_profile_config=None, request_first_season_only=False):
        """
        Initializes the SeerClient with the API URL and logs in the user.
        :param anime_profile_config: Dict with anime/default profile routing settings.
            Expected keys: 'anime_movie', 'anime_tv', optionally 'default_movie', 'default_tv'.
            Each value is a dict with optional keys: serverId, profileId, rootFolder, tags, languageProfileId.
        """
        super().__init__()
        self.api_url = api_url
        self.api_key = api_key
        self.username = seer_user_name
        self.password = seer_password
        self.session_token = session_token
        self.is_logged_in = False
        self._login_lock = None
        self.number_of_seasons = number_of_seasons
        self.request_first_season_only = _as_bool(request_first_season_only)
        self.pending_requests = set()
        self.exclude_downloaded = exclude_downloaded
        self.exclude_requested = exclude_watched
        self.anime_profile_config = anime_profile_config or {}
        self.logger.debug("SeerClient initialized with API URL: %s", api_url)

    def _resolve_tv_seasons(self):
        """Return Seer seasons payload for TV requests."""
        if self.request_first_season_only:
            return [1]

        if self.number_of_seasons in (None, "", "all", 0, "0"):
            return "all"

        return list(range(1, int(self.number_of_seasons) + 1))
        
    async def init(self):
        """
        Asynchronous initialization method to fetch all requests.
        This is typically called after creating an instance of SeerClient
        to ensure that the requests cache is populated.
        """
        self.logger.debug("Initializing SeerClient...")
        await self.fetch_all_requests()

    def _get_auth_headers(self, use_cookie):
        """Prepare headers and cookies based on `use_cookie` flag."""
        headers = {'Content-Type': 'application/json', 'accept': 'application/json'}
        cookies = {}

        if use_cookie and self.session_token:
            cookies['connect.sid'] = self.session_token
        elif not use_cookie:
            headers['X-Api-Key'] = self.api_key

        return headers, cookies

    async def _make_request(self, method, endpoint, data=None, use_cookie=False, retries=3, delay=2):
        """Unified API request handling with retry logic and error handling."""
        url = f"{self.api_url}/{endpoint}"
        for attempt in range(retries):
            self.logger.debug("Attempt %d for request to %s", attempt + 1, url)

            headers, cookies = self._get_auth_headers(use_cookie)

            # Use shared session but override headers/cookies for this request
            # since aiohttp allows passing request-level headers/cookies
            session = await self._get_session()
            try:
                async with session.request(method, url, json=data, headers=headers, cookies=cookies, timeout=self.REQUEST_TIMEOUT) as response:
                    self.logger.debug("Received response with status %d for request to %s", response.status, url)
                    if response.status in HTTP_OK:
                        return await response.json()
                    elif response.status == 403:
                        resp = await response.json()
                        message = resp.get('message') or resp.get('error', '')
                        self.logger.error(
                            f"Request to {url} failed with status: {response.status}, {message}"
                        )
                        # Quota/permission errors won't be resolved by repeated login attempts.
                        lower_message = message.lower()
                        if (
                            'quota' in lower_message
                            or 'permission' in lower_message
                            or 'not authorized' in lower_message
                        ):
                            return None
                        # Otherwise treat as auth failure and retry with login
                        if attempt < retries - 1:
                            self.logger.debug("Retrying login due to 403")
                            await self.login()
                        else:
                            return None
                    elif response.status == 404 and attempt < retries - 1:
                        self.logger.debug("Retrying login due to status 404")
                        await self.login()
                    else:
                        resp = await response.json()
                        self.logger.error(
                            f"Request to {url} failed with status: {response.status}, {resp.get('message') or resp.get('error', 'Unknown error')}"
                        )
            except aiohttp.ClientError as e:
                self.logger.error(f"Client error during request to {url}: {e}")
            await asyncio.sleep(delay)
        return None

    async def login(self):
        """Authenticate with the Seer service and obtain a session token."""
        if self._login_lock is None:
            self._login_lock = asyncio.Lock()

        async with self._login_lock:
            if self.is_logged_in:
                self.logger.debug("Already logged in.")
                return

        login_url = f"{self.api_url}/api/v1/auth/local"
        self.logger.debug("Logging in to %s", login_url)
        session = await self._get_session()
        try:
            async with session.post(login_url, json={"email": self.username, "password": self.password}, timeout=self.REQUEST_TIMEOUT) as response:
                self.logger.debug("Login response status: %d", response.status)
                if response.status in self.HTTP_OK and 'connect.sid' in response.cookies:
                    self.session_token = response.cookies['connect.sid'].value
                    self.is_logged_in = True
                    self.logger.info("Successfully logged in as %s", self.username)
                else:
                    self.session_token = None
                    self.is_logged_in = False
                    self.logger.error("Login failed: %d", response.status)
        except asyncio.TimeoutError:
            self.session_token = None
            self.is_logged_in = False
            self.logger.error("Login request to %s timed out.", login_url)

    async def get_all_users(self, max_users=100):
        """Fetch all users from the Seer service API, returning a list of user IDs, names, and local status."""
        self.logger.debug("Fetching all users with max_users=%d", max_users)
        data = await self._make_request("GET", f"api/v1/user?take={max_users}")
        if data:
            self.logger.debug("Fetched users data: %s", data)
            return [
                {
                    'id': user['id'],
                    'name': user.get('displayName', user.get('jellyfinUsername', 'Unknown User')),
                    'email': user.get('email'),
                    'isLocal': user.get('plexUsername') is None and user.get('jellyfinUsername') is None
                }
                for user in data.get('results', [])
            ]
        return []
    
    async def fetch_all_requests(self):
        """Fetch all requests made in the Seer service and save them to the database."""
        self.logger.debug("Fetching all requests...")
        total_requests = await self.get_total_request()
        self.logger.debug("Total requests to fetch: %d", total_requests)
        tasks = [self._fetch_batch(skip) for skip in range(0, total_requests, BATCH_SIZE)]
        batches = await asyncio.gather(*tasks)
        if all(batch is not None for batch in batches):
            live_keys = set().union(*batches) if batches else set()
            DatabaseManager().reconcile_seer_requests(live_keys)
        self.logger.info("Fetched all requests and saved to database.")

    async def _fetch_batch(self, skip):
        """Fetch a batch of requests and save them to the database."""
        self.logger.debug("Fetching batch of requests starting at skip=%d", skip)
        try:
            data = await self._make_request("GET", f"api/v1/request?take={BATCH_SIZE}&skip={skip}")
            if data:
                requests = data.get('results', [])
                DatabaseManager().save_requests_batch(requests)
                return {
                    (str((request.get('media') or {}).get('tmdbId')), (request.get('media') or {}).get('mediaType'))
                    for request in requests
                    if (request.get('media') or {}).get('tmdbId') is not None
                    and (request.get('media') or {}).get('mediaType')
                }
        except Exception as e:
            self.logger.error(f"Failed to fetch batch at skip {skip}: {e}")
        return None

    async def get_total_request(self):
        """Get total requests made in the Seer service."""
        self.logger.debug("Getting total request count...")
        data = await self._make_request("GET", "api/v1/request/count")
        total = data.get('total', 0) if data else 0
        self.logger.debug("Total requests count: %d", total)
        return total

    @staticmethod
    def _is_pending_request(request_data):
        """Return True when a Seer request still awaits approve/deny."""
        status = request_data.get('status') if isinstance(request_data, dict) else None
        return status in PENDING_REQUEST_STATUSES

    async def has_pending_requests(self) -> bool:
        """Check Seer for any request still pending approval/denial."""
        self.logger.debug("Checking Seer for pending requests...")
        total_requests = await self.get_total_request()
        for skip in range(0, total_requests, BATCH_SIZE):
            data = await self._make_request("GET", f"api/v1/request?take={BATCH_SIZE}&skip={skip}")
            if not data:
                continue
            for request_data in data.get('results', []):
                if self._is_pending_request(request_data):
                    self.logger.info("Found pending Seer request; job should pause.")
                    return True
        return False

    async def get_requests_index(self) -> dict:
        """Build a lookup of Seer requests keyed by (media_type, tmdb_id).

        :return: Dict mapping ``(media_type, tmdb_id)`` tuples to lists of
            request entries with ``id``, ``status``, and ``media_status``.
        """
        self.logger.debug("Building Seer requests index...")
        index: dict = {}
        total_requests = await self.get_total_request()
        for skip in range(0, total_requests, BATCH_SIZE):
            data = await self._make_request("GET", f"api/v1/request?take={BATCH_SIZE}&skip={skip}")
            if not data:
                continue
            for request_data in data.get('results', []):
                media = request_data.get('media') or {}
                tmdb_id = media.get('tmdbId')
                media_type = media.get('mediaType')
                if tmdb_id is None or not media_type:
                    continue
                key = (str(media_type).lower(), str(tmdb_id))
                entry = {
                    'id': request_data.get('id'),
                    'status': request_data.get('status'),
                    'media_status': media.get('status'),
                    'created_at': request_data.get('createdAt'),
                    'updated_at': request_data.get('updatedAt'),
                    'title': media.get('title') or request_data.get('title'),
                }
                index.setdefault(key, []).append(entry)
        self.logger.debug("Seer requests index built with %d keys", len(index))
        return index

    async def approve_request(self, request_id: int) -> bool:
        """Approve a Seer media request by its numeric request id.

        :param request_id: Seer request id.
        :return: True when the approve call succeeds.
        """
        self.logger.debug("Approving Seer request %s", request_id)
        result = await self._make_request(
            "POST", f"api/v1/request/{request_id}/approve", use_cookie=False,
        )
        return result is not None

    async def decline_request(self, request_id: int) -> bool:
        """Decline a Seer media request by its numeric request id.

        :param request_id: Seer request id.
        :return: True when the decline call succeeds.
        """
        self.logger.debug("Declining Seer request %s", request_id)
        result = await self._make_request(
            "POST", f"api/v1/request/{request_id}/decline", use_cookie=False,
        )
        return result is not None

    async def delete_request(self, request_id: int) -> bool:
        """Delete a Seer media request record by its numeric request id.

        :param request_id: Seer request id.
        :return: True when the delete call succeeds.
        """
        url = f"{self.api_url}/api/v1/request/{int(request_id)}"
        headers, cookies = self._get_auth_headers(bool(self.session_token))
        session = await self._get_session()
        try:
            async with session.delete(url, headers=headers, cookies=cookies, timeout=self.REQUEST_TIMEOUT) as response:
                if response.status in (200, 202, 204):
                    self.logger.info("Deleted Seer request %s", request_id)
                    return True
                body = ""
                try:
                    body = await response.text()
                except Exception:
                    pass
                self.logger.error(
                    "Failed to delete Seer request %s: status=%s body=%s",
                    request_id,
                    response.status,
                    body[:200],
                )
                return False
        except aiohttp.ClientError as exc:
            self.logger.error("Client error deleting Seer request %s: %s", request_id, exc)
            return False

    async def get_radarr_servers(self):
        """Fetch available Radarr servers from the Seer service with their profiles, root folders, and tags."""
        self.logger.debug("Fetching Radarr servers from the Seer service")
        return await self._make_request("GET", "api/v1/service/radarr")

    async def get_sonarr_servers(self):
        """Fetch available Sonarr servers from the Seer service with their profiles, root folders, and tags."""
        self.logger.debug("Fetching Sonarr servers from the Seer service")
        return await self._make_request("GET", "api/v1/service/sonarr")

    async def _fetch_server_defaults(self, media_type: str, server_id) -> dict:
        """Fetch default profileId and rootFolder from Jellyseerr for the given media type.

        Calls the Radarr (movie) or Sonarr (tv) service endpoint and returns the
        active profile ID and root folder for the specified server.  Falls back to
        the default-flagged server, then the first server in the list.

        :param media_type: ``'movie'`` (Radarr) or ``'tv'`` (Sonarr).
        :param server_id: Target server ID to match, or ``None`` for
            the default/first server.
        :return: Dict with ``'profileId'`` and ``'rootFolder'`` keys; values may
            be ``None`` when Jellyseerr itself has no defaults configured.
        """
        try:
            servers = (
                await self.get_radarr_servers()
                if media_type == 'movie'
                else await self.get_sonarr_servers()
            )
            if not servers:
                service_name = 'Radarr' if media_type == 'movie' else 'Sonarr'
                self.logger.warning(
                    "No %s servers found while fetching defaults.", service_name
                )
                return {}

            # Prefer exact server-ID match → default-flagged server → first entry
            server = (
                next((s for s in servers if s.get('id') == server_id), None)
                or next((s for s in servers if s.get('isDefault')), None)
                or servers[0]
            )

            profile_id = server.get('activeProfileId')
            root_folder = server.get('activeDirectory')

            # Last-resort: pick the first available profile / root folder
            if profile_id is None and server.get('profiles'):
                profile_id = server['profiles'][0].get('id')
            if root_folder is None and server.get('rootFolders'):
                root_folder = server['rootFolders'][0].get('path')

            self.logger.debug(
                "Fetched server defaults for %s (serverId=%s): profileId=%s, rootFolder=%s",
                media_type, server_id, profile_id, root_folder,
            )
            return {'profileId': profile_id, 'rootFolder': root_folder}
        except Exception as exc:
            self.logger.error(
                "Failed to fetch server defaults for media_type=%s: %s", media_type, exc
            )
            return {}

    def _apply_profile_config(self, data, profile_key, media_type):
        """Apply profile configuration (serverId, profileId, rootFolder, tags) to request data."""
        profile = self.anime_profile_config.get(profile_key, {})
        if not profile:
            return

        for key in ['serverId', 'profileId', 'rootFolder', 'tags']:
            if key in profile:
                data[key] = profile[key]
        if media_type == 'tv' and 'languageProfileId' in profile:
            data['languageProfileId'] = profile['languageProfileId']

        self.logger.info("Applied profile '%s': serverId=%s, profileId=%s, rootFolder=%s",
                        profile_key, profile.get('serverId'), profile.get('profileId'), profile.get('rootFolder'))

    def _build_seer_payload(self, media_type, media, source=None, user=None,
                            is_anime=False, rationale=None):
        """Build the Seer request payload dict.

        Private meta-keys (prefixed with ``_``) are stripped before the payload is
        sent to Seer but are preserved in the queue row so the worker can call
        ``save_request`` correctly after a successful submission.
        Metadata objects are intentionally excluded — they are persisted via
        ``save_metadata`` at enqueue time so the payload stays small.

        :return: payload dict ready for JSON serialisation.
        """
        data = {"mediaType": media_type, "mediaId": media['id']}

        if media_type == 'tv':
            data["seasons"] = self._resolve_tv_seasons()

        if self.anime_profile_config:
            profile_key = f"anime_{media_type}" if is_anime else f"default_{media_type}"
            self._apply_profile_config(data, profile_key, media_type)

        # Private meta-keys — consumed by the worker, not sent to Seer
        data["_source_id"] = source.get('id') if source else None
        data["_source_origin"] = source.get('_source_origin') if source else None
        data["_user_id"] = user.get('id') if user else None
        data["_rationale"] = rationale
        data["_is_anime"] = is_anime

        return data

    async def request_media(self, media_type, media, source=None, tvdb_id=None, user=None, is_anime=False, rationale=None):
        """Enqueue a Seer submission for reliable background delivery.

        Replaces the old direct-submit behaviour. All pre-checks (already requested /
        downloaded / streaming-excluded) are still performed by the caller (handler
        layer) before this method is invoked.

        :return: True if the item was newly enqueued, False if skipped (duplicate or
            already submitted).
        """
        tmdb_id = str(media['id'])

        # Fast intra-process guard (asyncio is single-threaded: check+add are atomic)
        if (media_type, tmdb_id) in self.pending_requests:
            self.logger.debug("Skipping duplicate request for %s (ID: %s)", media_type, tmdb_id)
            return False

        db = DatabaseManager()

        # Double-check DB to close the TOCTOU gap between the handler's
        # check_already_requested() call and this point.
        if self.exclude_requested and db.check_request_exists(media_type, tmdb_id):
            self.logger.debug(
                "Skipping %s (ID: %s): already in DB (concurrent submission).", media_type, tmdb_id
            )
            return False

        # Mark in-memory to short-circuit further calls within this run
        self.pending_requests.add((media_type, tmdb_id))

        payload = self._build_seer_payload(media_type, media, source=source, user=user,
                                           is_anime=is_anime, rationale=rationale)
        user_id = user.get('id') if user else None

        if user:
            db.save_user(user)

        # Persist metadata immediately while the full objects are available in memory,
        # so the payload stored in the queue table stays compact (no large text blobs).
        try:
            from api_service.services.ratings.enrichment import enrich_and_save_metadata
            await enrich_and_save_metadata(media, media_type, db)
        except Exception:
            try:
                db.save_metadata(media, media_type)
            except Exception:
                pass
        if source and is_tmdb_metadata_source_id(source.get("id")):
            try:
                from api_service.services.ratings.enrichment import enrich_and_save_metadata
                await enrich_and_save_metadata(source, media_type, db)
            except Exception:
                try:
                    db.save_metadata(source, media_type)
                except Exception:
                    pass

        enqueued = db.enqueue_request(tmdb_id, media_type, user_id, payload)
        if enqueued:
            self.logger.info("Enqueued %s tmdb:%s for Seer delivery.", media_type, tmdb_id)
        return enqueued

    async def submit_queued_request(self, payload: dict) -> bool:
        """Perform the actual HTTP submission to Seer for a single queue row.

        Called by the queue worker.  Strips private meta-keys before sending.
        Validates ``profileId`` and ``rootFolder`` before the HTTP call, and
        attempts to resolve them from Jellyseerr server settings when either is
        absent or ``None``.

        :param payload: The JSON-decoded payload stored in pending_requests.
        :return: True on HTTP success, False on any failure.
        """
        # Build clean Seer body (drop private meta-keys)
        data = {k: v for k, v in payload.items() if not k.startswith('_')}
        media_type = data.get('mediaType', 'unknown')
        media_id = data.get('mediaId')

        # Attempt to fill missing profileId / rootFolder from Jellyseerr server settings
        if data.get('profileId') is None or data.get('rootFolder') is None:
            server_id = data.get('serverId')
            self.logger.warning(
                "profileId or rootFolder missing for %s tmdb:%s (serverId=%s) — "
                "fetching defaults from Jellyseerr.",
                media_type, media_id, server_id,
            )
            defaults = await self._fetch_server_defaults(media_type, server_id)
            if data.get('profileId') is None:
                data['profileId'] = defaults.get('profileId')
            if data.get('rootFolder') is None:
                data['rootFolder'] = defaults.get('rootFolder')

        # Abort if required fields are still absent after the fallback
        if data.get('profileId') is None:
            self.logger.error(
                "Cannot submit Jellyseerr request for %s tmdb:%s — "
                "profileId is missing (serverId=%s, rootFolder=%s). "
                "Configure a valid profileId in your anime/default profile settings.",
                media_type, media_id, data.get('serverId'), data.get('rootFolder'),
            )
            return False
        if data.get('rootFolder') is None:
            self.logger.error(
                "Cannot submit Jellyseerr request for %s tmdb:%s — "
                "rootFolder is missing (serverId=%s, profileId=%s). "
                "Configure a valid rootFolder in your anime/default profile settings.",
                media_type, media_id, data.get('serverId'), data.get('profileId'),
            )
            return False

        self.logger.debug("Sending Jellyseerr request: %s", data)
        # Saved cookies can expire or belong to a previously selected user.
        # Refresh when credentials exist so queued jobs run as the configured
        # Jellyseerr user instead of silently falling back to a stale session.
        if self.username and self.password:
            await self.login()
            if not self.session_token:
                self.logger.error(
                    "Cannot submit Jellyseerr request for %s tmdb:%s — "
                    "configured Seer user login failed. Re-authenticate the Seer user in settings.",
                    media_type, media_id,
                )
                return False

        response = await self._make_request(
            "POST", "api/v1/request", data=data, use_cookie=bool(self.session_token)
        )
        if response and 'error' not in response:
            self.logger.debug("Seer submission successful: %s", response)
            return True

        self.logger.error(
            "Jellyseerr request failed for %s tmdb:%s | "
            "response=%s | payload=%s",
            media_type, media_id, response, data,
        )
        return False
            
    async def check_already_requested(self, tmdb_id, media_type):
        """Check if a media request is cached in the current cycle."""
        if self.exclude_requested:
            self.logger.debug("Checking if media already requested: tmdb_id=%s, media_type=%s", tmdb_id, media_type)

            try:
                result = DatabaseManager().check_request_exists(media_type, tmdb_id)

                if not isinstance(result, bool):
                    self.logger.warning("Unexpected return value from check_request_exists: %s", result)
                    return False

                return result
            except Exception as e:
                self.logger.error("Error checking if media already requested: %s", e, exc_info=True)
        else:
            self.logger.info("Skipping check for already requested media.")
        
        return False

    async def check_requests_exist_batch(self, media_type: str, tmdb_ids: List[str]) -> Set[str]:
        """Check which of the provided TMDB IDs already have requests in the database."""
        if not self.exclude_requested or not tmdb_ids:
            return set()
        
        try:
            return DatabaseManager().check_requests_exist_batch(media_type, tmdb_ids)
        except Exception as e:
            self.logger.error("Error in bulk check requests: %s", e)
            return set()

    async def check_already_downloaded(self, tmdb_id, media_type, local_content=None):
        """Check if a media item has already been downloaded based on local content."""
        if self.exclude_downloaded:
            self.logger.debug("Checking if media already downloaded: tmdb_id=%s, media_type=%s", tmdb_id, media_type)

            if local_content is None:
                self.logger.warning("local_content is None, skipping downloaded check")
                return False

            # Optimization: If local_content is a list, we should ideally have a set for O(1) lookup.
            # However, since this is called per item, we'll check if we can optimize the caller side later.
            # For now, let's at least make sure we don't do redundant work here.
            items = local_content.get(media_type, [])
            if isinstance(items, set):
                return str(tmdb_id) in items
            
            if not isinstance(items, list):
                self.logger.warning("Expected list or set for media_type '%s', but got %s", media_type, type(items))
                return False

            for item in items:
                if isinstance(item, dict) and item.get('tmdb_id') == str(tmdb_id):
                    return True
                if isinstance(item, str) and item == str(tmdb_id):
                    return True
        else:
            self.logger.info("Skipping check for already downloaded media.")

        return False

    async def get_metadata(self, media_id, media_type):
        """Retrieve metadata for a specific media item."""
        self.logger.debug("Getting metadata for media_id=%s, media_type=%s", media_id, media_type)
        return DatabaseManager().get_metadata(media_id, media_type)

    async def lookup_seer_media_id(self, tmdb_id, media_type):
        """Resolve TMDB id to Seer's internal mediaInfo.id (None if not present in Seer)."""
        data = await self._fetch_media_detail_payload(tmdb_id, media_type)
        if not data:
            return None
        media_info = data.get("mediaInfo") or {}
        return media_info.get("id")

    async def _fetch_media_detail_payload(self, tmdb_id, media_type):
        """Fetch raw Seer/Jellyseerr media detail payload for a TMDB id."""
        endpoint = f"api/v1/{'movie' if media_type == 'movie' else 'tv'}/{int(tmdb_id)}"
        return await self._make_request("GET", endpoint, use_cookie=bool(self.session_token))

    @staticmethod
    def _pick_trailer(related_videos):
        """Return the best YouTube trailer key and URL from Seer relatedVideos."""
        videos = related_videos or []
        trailer = next(
            (
                video for video in videos
                if str(video.get("site", "")).lower() == "youtube"
                and str(video.get("type", "")).lower() == "trailer"
                and video.get("key")
            ),
            None,
        )
        if trailer:
            key = trailer["key"]
            return key, f"https://www.youtube.com/watch?v={key}"

        fallback = next(
            (
                video for video in videos
                if str(video.get("site", "")).lower() == "youtube" and video.get("key")
            ),
            None,
        )
        if fallback:
            key = fallback["key"]
            return key, f"https://www.youtube.com/watch?v={key}"
        return None, None

    @classmethod
    def _pick_trailer_url(cls, related_videos):
        """Return the best YouTube trailer URL from Seer relatedVideos."""
        _, url = cls._pick_trailer(related_videos)
        return url

    _CREW_JOBS = frozenset({
        "writer",
        "screenplay",
        "story",
        "novel",
        "producer",
        "executive producer",
    })

    @classmethod
    def _format_crew(cls, credits):
        """Return top crew members for key writing/production roles."""
        crew = []
        seen = set()
        for member in credits.get("crew") or []:
            name = member.get("name")
            job = member.get("job") or ""
            if not name:
                continue
            if str(job).lower() == "director":
                continue
            if str(job).lower() not in cls._CREW_JOBS:
                continue
            key = (name, job)
            if key in seen:
                continue
            seen.add(key)
            crew.append({"name": name, "job": job})
            if len(crew) >= 6:
                break
        return crew

    @staticmethod
    def _resolve_imdb_id(data):
        """Resolve an IMDb id from Seer detail payload fields."""
        external_ids = data.get("externalIds") or {}
        return data.get("imdbId") or external_ids.get("imdbId") or external_ids.get("imdb_id") or ""

    @staticmethod
    def _pick_content_rating(data, media_type, preferred_regions=("US", "TR", "GB")):
        """Pick the best content rating/certification from Seer movie or TV payload."""
        if media_type == "movie":
            releases = data.get("releases") or {}
            for region in preferred_regions:
                for entry in releases.get("results") or []:
                    if entry.get("iso_3166_1") != region:
                        continue
                    for release in entry.get("release_dates") or []:
                        certification = release.get("certification")
                        if certification:
                            return certification
            return None

        ratings = data.get("contentRatings") or {}
        for region in preferred_regions:
            for entry in ratings.get("results") or []:
                if entry.get("iso_3166_1") == region and entry.get("rating"):
                    return entry["rating"]
        for entry in ratings.get("results") or []:
            if entry.get("rating"):
                return entry["rating"]
        return None

    @staticmethod
    def _format_watch_providers(watch_providers, preferred_regions=("US", "TR", "GB")):
        """Return deduplicated streaming providers for the first matching region."""
        providers = watch_providers or []
        region_entry = None
        for region in preferred_regions:
            region_entry = next(
                (entry for entry in providers if entry.get("iso_3166_1") == region),
                None,
            )
            if region_entry:
                break
        if region_entry is None and providers:
            region_entry = providers[0]
        if not region_entry:
            return []

        formatted = []
        seen = set()
        for key in ("flatrate", "rent", "buy"):
            for item in region_entry.get(key) or []:
                name = item.get("name") or item.get("providerName")
                if not name or name in seen:
                    continue
                seen.add(name)
                formatted.append({
                    "name": name,
                    "logo_path": tmdb_image_url(
                        item.get("logoPath") or item.get("logo_path"),
                        "w45",
                    ),
                })
        return formatted[:8]

    @staticmethod
    def _extract_keywords(data):
        """Extract keyword names from Seer movie or TV keyword payloads."""
        keywords = data.get("keywords")
        if isinstance(keywords, list):
            items = keywords
        elif isinstance(keywords, dict):
            items = keywords.get("keywords") or []
        else:
            return []
        return [item.get("name") for item in items if item.get("name")][:6]

    @classmethod
    def _format_media_details(cls, data, media_type):
        """
        Map Seer media detail payload into a normalized metadata dict.

        :param data: Raw Seer API response for movie/tv detail.
        :param media_type: ``movie`` or ``tv``.
        :return: Normalized metadata fields for the request details UI.
        """
        genres = [genre.get("name") for genre in data.get("genres", []) if genre.get("name")]
        credits = data.get("credits") or {}
        cast = []
        for member in (credits.get("cast") or [])[:16]:
            name = member.get("name")
            if not name:
                continue
            cast.append({
                "name": name,
                "character": member.get("character") or "",
                "profile_path": tmdb_image_url(member.get("profilePath"), "w185"),
            })

        if media_type == "movie":
            crew = credits.get("crew") or []
            directors = [
                member.get("name")
                for member in crew
                if str(member.get("job", "")).lower() == "director" and member.get("name")
            ]
            runtime = data.get("runtime")
            seasons_count = None
            episodes_count = None
            networks = []
            release_date = data.get("releaseDate") or ""
            original_title = data.get("originalTitle") or ""
            last_air_date = ""
            next_air_date = ""
            in_production = False
        else:
            directors = [
                creator.get("name")
                for creator in data.get("createdBy", [])
                if creator.get("name")
            ]
            run_times = data.get("episodeRunTime") or []
            runtime = run_times[0] if run_times else None
            seasons_count = data.get("numberOfSeasons") or data.get("numberOfSeason")
            episodes_count = data.get("numberOfEpisodes")
            networks = [
                network.get("name")
                for network in data.get("networks", [])
                if network.get("name")
            ]
            release_date = data.get("firstAirDate") or ""
            original_title = data.get("originalName") or ""
            last_air_date = data.get("lastAirDate") or ""
            next_episode = data.get("nextEpisodeToAir") or {}
            next_air_date = next_episode.get("airDate") or ""
            in_production = bool(data.get("inProduction"))

        trailer_key, trailer_url = cls._pick_trailer(data.get("relatedVideos"))
        production_companies = [
            company.get("name")
            for company in data.get("productionCompanies", [])[:4]
            if company.get("name")
        ]
        raw_collection = data.get("collection") or {}
        collection_name = raw_collection.get("name") or ""
        collection_id = raw_collection.get("id")
        collection = None
        if collection_id or collection_name:
            collection = {
                "id": int(collection_id) if collection_id is not None else None,
                "name": collection_name,
                "parts": [],
            }
        keywords = cls._extract_keywords(data)

        return {
            "available": True,
            "tmdb_id": str(data.get("id") or ""),
            "media_type": media_type,
            "title": data.get("title") or data.get("name") or "",
            "original_title": original_title,
            "original_language": data.get("originalLanguage") or "",
            "tagline": data.get("tagline") or "",
            "overview": data.get("overview") or "",
            "status": data.get("status") or "",
            "release_date": release_date,
            "content_rating": cls._pick_content_rating(data, media_type),
            "genres": genres,
            "keywords": keywords,
            "runtime": runtime,
            "director": directors,
            "crew": cls._format_crew(credits),
            "cast": cast,
            "imdb_id": cls._resolve_imdb_id(data),
            "trailer": trailer_url,
            "trailer_key": trailer_key,
            "backdrop_path": tmdb_image_url(data.get("backdropPath"), "w1280"),
            "homepage": data.get("homepage") or "",
            "collection": collection,
            "networks": networks if media_type == "tv" else [],
            "seasons_count": seasons_count if media_type == "tv" else None,
            "episodes_count": episodes_count if media_type == "tv" else None,
            "last_air_date": last_air_date if media_type == "tv" else "",
            "next_air_date": next_air_date if media_type == "tv" else "",
            "in_production": in_production if media_type == "tv" else False,
            "production_companies": production_companies,
            "watch_providers": cls._format_watch_providers(data.get("watchProviders")),
        }

    @classmethod
    def _format_collection_part(cls, part):
        """Normalize one Seer/TMDB collection part into UI-ready fields."""
        media_info = part.get("mediaInfo") or {}
        requests = media_info.get("requests") or []
        primary_request = requests[0] if requests else {}
        request_status = primary_request.get("status")
        media_status = media_info.get("status")
        seer_status = derive_seer_status(request_status, media_status)
        can_request = (
            seer_status in {"not_found", "declined", "failed", "deleted"}
            and media_status not in AVAILABLE_MEDIA_STATUSES
        )
        return {
            "tmdb_id": str(part.get("id") or ""),
            "media_type": "movie",
            "title": part.get("title") or "",
            "overview": part.get("overview") or "",
            "release_date": part.get("releaseDate") or "",
            "poster_path": tmdb_image_url(part.get("posterPath"), "w342"),
            "seer_status": seer_status,
            "can_request": can_request,
        }

    @classmethod
    def _format_collection_details(cls, data):
        """
        Map Seer collection payload into a normalized dict with requestable parts.

        :param data: Raw Seer ``GET /api/v1/collection/{id}`` response.
        :return: Normalized collection metadata for the request details UI.
        """
        parts = [
            cls._format_collection_part(part)
            for part in (data.get("parts") or [])
            if part and part.get("id") is not None
        ]
        return {
            "id": data.get("id"),
            "name": data.get("name") or "",
            "overview": data.get("overview") or "",
            "parts": parts,
        }

    async def get_collection_details(self, collection_id):
        """
        Fetch a TMDB movie collection (with parts) from Seer.

        :param collection_id: TMDB collection id.
        :return: Normalized collection dict, or None when Seer has no payload.
        """
        if collection_id is None:
            return None
        data = await self._make_request(
            "GET",
            f"api/v1/collection/{int(collection_id)}",
            use_cookie=bool(self.session_token),
        )
        if not data:
            return None
        return self._format_collection_details(data)

    async def get_media_details(self, tmdb_id, media_type):
        """
        Fetch rich media metadata from Seer's movie/tv detail endpoint.

        When the movie belongs to a collection, also load collection parts so the
        details UI can list sibling titles and request them.

        :param tmdb_id: TMDB id for the requested item.
        :param media_type: ``movie`` or ``tv``.
        :return: Normalized metadata dict, or None when Seer has no detail payload.
        """
        data = await self._fetch_media_detail_payload(tmdb_id, media_type)
        if not data:
            return None
        details = self._format_media_details(data, media_type)
        details["seer_url"] = (
            f"{self.api_url.rstrip('/')}/{'movie' if media_type == 'movie' else 'tv'}/{int(tmdb_id)}"
        )
        collection = details.get("collection")
        if media_type == "movie" and isinstance(collection, dict) and collection.get("id"):
            collection_details = await self.get_collection_details(collection["id"])
            if collection_details:
                details["collection"] = {
                    **collection,
                    "name": collection_details.get("name") or collection.get("name") or "",
                    "overview": collection_details.get("overview") or "",
                    "parts": collection_details.get("parts") or [],
                }
        return details

    async def delete_media_file_by_tmdb(self, tmdb_id, media_type):
        """Delete files (via arr) for the Seer media matching tmdb_id. Returns True on success."""
        seer_media_id = await self.lookup_seer_media_id(tmdb_id, media_type)
        if not seer_media_id:
            self.logger.info("No Seer media found for tmdb_id=%s media_type=%s; nothing to delete.", tmdb_id, media_type)
            return False
        url = f"{self.api_url}/api/v1/media/{int(seer_media_id)}/file"
        headers, cookies = self._get_auth_headers(bool(self.session_token))
        session = await self._get_session()
        try:
            async with session.delete(url, headers=headers, cookies=cookies, timeout=self.REQUEST_TIMEOUT) as response:
                if response.status in (200, 202, 204):
                    self.logger.info("Deleted Seer media file for tmdb_id=%s (seer_media_id=%s)", tmdb_id, seer_media_id)
                    return True
                body = ""
                try:
                    body = await response.text()
                except Exception:
                    pass
                self.logger.error("Failed to delete Seer media file: status=%s body=%s", response.status, body[:200])
                return False
        except aiohttp.ClientError as exc:
            self.logger.error("Client error deleting Seer media file: %s", exc)
            return False
