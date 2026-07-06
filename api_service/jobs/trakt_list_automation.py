"""
Trakt List Automation for executing trakt_list jobs.
Fetches items from a Trakt custom list or watchlist and requests new items via Seer.
"""
import traceback
from typing import Any, Dict, List, Optional, Tuple

from api_service.config.logger_manager import LoggerManager
from api_service.db.database_manager import DatabaseManager
from api_service.db.job_repository import JobRepository
from api_service.jobs.discover_automation import ExecutionResult
from api_service.jobs._trakt_automation_base import TraktJobAutomationBase
from api_service.services.config_service import ConfigService
from api_service.services.request_sources import TRAKT_LIST_SOURCE
from api_service.services.trakt.media_user_augmentor import TraktAccountResolver
from api_service.services.trakt.trakt_client import TraktClient

MAX_FETCH_PAGES = 50
PAGE_SIZE = 100


class TraktListAutomation(TraktJobAutomationBase):
    """Automates fetching Trakt list items and requesting new media via Seer."""

    def __init__(self):
        """Initialize with logger only. Use create() for full initialization."""
        super().__init__()
        self.trakt_client: Optional[TraktClient] = None
        self.list_user: Optional[str] = None
        self.list_ref: Optional[str] = None
        self.use_watchlist: bool = False
        self.authenticated: bool = False

    @classmethod
    async def create(cls, job_id: int, dry_run: bool = False) -> "TraktListAutomation":
        """Create and initialize TraktListAutomation for a job.

        Args:
            job_id: ID of the trakt_list job to execute.
            dry_run: If True, skip request-cache sync during initialization.

        Returns:
            Initialized TraktListAutomation instance.

        Raises:
            ValueError: If the job is missing or misconfigured.
        """
        instance = cls()
        instance.job_id = job_id
        instance.repository = JobRepository()
        instance.db_manager = DatabaseManager()
        instance.env_vars = ConfigService.get_runtime_config()

        instance.job_data = instance.repository.get_job(job_id)
        if not instance.job_data:
            raise ValueError(f"Job not found: {job_id}")
        if instance.job_data.get("job_type") != "trakt_list":
            raise ValueError(f"Job {job_id} is not a trakt_list job")

        instance.logger.info(
            "Initializing TraktListAutomation for job: %s",
            instance.job_data["name"],
        )
        await instance._initialize_components(dry_run=dry_run)
        instance.logger.info("TraktListAutomation initialized successfully")
        return instance

    async def _initialize_components(self, dry_run: bool = False) -> None:
        """Initialize Seer, Trakt, and TMDb clients from job configuration."""
        await self._initialize_shared_components(dry_run=dry_run)
        dedup_mode = str(self.job_data.get("filters", {}).get("dedup_mode") or "global").strip()
        if dedup_mode == "per_list" and self.seer_client:
            # Per-list dedup only skips items seen on this list; allow re-request elsewhere.
            self.seer_client.exclude_requested = False
        self.trakt_client, self.list_user, self.list_ref, self.use_watchlist, self.authenticated = (
            self._build_trakt_client_and_list_target()
        )

    def _resolve_list_target(self) -> Tuple[Optional[str], str, bool]:
        """Resolve list username, reference, and whether the watchlist is targeted."""
        job_filters = self.job_data.get("filters", {})
        list_source = str(job_filters.get("list_source") or "public_url").strip()

        if list_source == "linked_user":
            user_ids = self.job_data.get("user_ids") or []
            if len(user_ids) != 1:
                raise ValueError("Trakt list job requires exactly one linked media user")
            if bool(job_filters.get("watchlist")):
                return "me", "watchlist", True
            list_ref = str(job_filters.get("list_ref") or job_filters.get("list_slug") or "").strip()
            if not list_ref:
                raise ValueError("Trakt list job requires a selected list")
            return "me", list_ref, False

        list_url = str(job_filters.get("list_url") or "").strip()
        if not list_url:
            raise ValueError("Trakt list job requires a list URL")
        list_user, list_ref = TraktClient.parse_list_url(list_url)
        if list_ref == "watchlist":
            return list_user or "me", "watchlist", True
        return list_user, list_ref, False

    def _build_trakt_client_and_list_target(
        self,
    ) -> Tuple[TraktClient, Optional[str], str, bool, bool]:
        """Build the Trakt client and resolve list target metadata."""
        job_filters = self.job_data.get("filters", {})
        list_source = str(job_filters.get("list_source") or "public_url").strip()
        list_user, list_ref, use_watchlist = self._resolve_list_target()
        client_id, client_secret = self._get_trakt_app_credentials()

        if list_source == "linked_user":
            user_ids = self.job_data.get("user_ids") or []
            provider = str(self.env_vars.get("SELECTED_SERVICE") or "").lower()
            external_user_id = str(user_ids[0])
            identity = self.db_manager.get_media_user_identity(provider, external_user_id)
            resolved = TraktAccountResolver(self.db_manager).resolve(identity["id"])
            if not resolved:
                raise ValueError(
                    f"Media user {external_user_id} has no connected Trakt account"
                )
            client = TraktClient(
                client_id,
                client_secret,
                access_token=resolved.get("access_token", ""),
                refresh_token=resolved.get("refresh_token", ""),
                expires_at=resolved.get("expires_at"),
                db=self.db_manager,
                link_id=resolved["id"],
                token_source=resolved.get("token_source", "manual_oauth"),
            )
            return client, list_user, list_ref, use_watchlist, True

        client = TraktClient(client_id, client_secret, db=self.db_manager)
        return client, list_user, list_ref, use_watchlist, False

    async def run(self, dry_run: bool = False) -> ExecutionResult:
        """Execute the Trakt list job.

        Args:
            dry_run: When True, simulate without enqueueing requests.

        Returns:
            ExecutionResult with execution details.
        """
        if not self.job_data:
            return ExecutionResult(
                success=False,
                results_count=0,
                requested_count=0,
                error_message="Job not initialized",
            )

        self.logger.info(
            "%sStarting trakt list job: %s",
            "[DRY RUN] " if dry_run else "",
            self.job_data["name"],
        )
        exec_id = None if dry_run else self.repository.log_execution_start(self.job_id)

        try:
            from contextlib import AsyncExitStack

            async with AsyncExitStack() as stack:
                if self.seer_client:
                    await stack.enter_async_context(self.seer_client)
                if self.tmdb_client:
                    await stack.enter_async_context(self.tmdb_client)
                    if self.tmdb_client.omdb_client:
                        await stack.enter_async_context(self.tmdb_client.omdb_client)
                if self.trakt_client:
                    await stack.enter_async_context(self.trakt_client)

                results = await self.fetch_list_items()
            results_count = len(results)
            self.logger.info("Fetched %d Trakt list items after filtering", results_count)

            requested_count, dry_run_items = await self.filter_and_request(results, dry_run=dry_run)

            if not dry_run:
                self.repository.log_execution_end(
                    exec_id=exec_id,
                    status="completed",
                    results_count=results_count,
                    requested_count=requested_count,
                )

            return ExecutionResult(
                success=True,
                results_count=results_count,
                requested_count=requested_count,
                dry_run_items=dry_run_items,
            )
        except Exception as exc:
            error_msg = str(exc) if str(exc) else type(exc).__name__
            self.logger.error("Job failed: %s", error_msg)
            self.logger.error("Traceback: %s", traceback.format_exc())

            if not dry_run and exec_id is not None:
                self.repository.log_execution_end(
                    exec_id=exec_id,
                    status="failed",
                    results_count=0,
                    requested_count=0,
                    error_message=error_msg,
                )

            return ExecutionResult(
                success=False,
                results_count=0,
                requested_count=0,
                error_message=error_msg,
            )

    async def fetch_list_items(self) -> List[Dict[str, Any]]:
        """Fetch and filter Trakt list items for the configured media types."""
        media_type = self.job_data.get("media_type", "movie")
        max_results = int(self.job_data.get("max_results") or 20)
        dedup_mode = str(self.job_data.get("filters", {}).get("dedup_mode") or "global").strip()
        per_list_seen = (
            self.db_manager.get_trakt_list_seen(self.job_id)
            if dedup_mode == "per_list"
            else set()
        )

        filtered: List[Dict[str, Any]] = []
        collected_keys: set[tuple[str, str]] = set()
        stats = {
            "pages_fetched": 0,
            "raw_items": 0,
            "duplicate_items": 0,
            "missing_tmdb_id": 0,
            "skipped_dedup": 0,
            "failed_quality_filter": 0,
            "kept": 0,
        }

        for page in range(1, MAX_FETCH_PAGES + 1):
            if self.use_watchlist:
                raw_items = await self.trakt_client.get_watchlist_items(
                    self.list_user or "me",
                    media_type,
                    limit=PAGE_SIZE,
                    page=page,
                    authenticated=self.authenticated,
                )
            else:
                raw_items = await self.trakt_client.get_list_items(
                    self.list_user,
                    self.list_ref,
                    media_type,
                    limit=PAGE_SIZE,
                    page=page,
                    authenticated=self.authenticated,
                )

            if not raw_items:
                break

            stats["pages_fetched"] = page
            stats["raw_items"] += len(raw_items)

            for item in raw_items:
                item_media_type = item.get("media_type") or media_type
                tmdb_id = item.get("tmdb_id")
                if not tmdb_id:
                    stats["missing_tmdb_id"] += 1
                    continue

                seen_key = (str(tmdb_id), item_media_type)
                if seen_key in collected_keys:
                    stats["duplicate_items"] += 1
                    continue
                collected_keys.add(seen_key)

                if await self._should_skip_fetch_item(
                    item_media_type,
                    tmdb_id,
                    dedup_mode,
                    per_list_seen,
                ):
                    stats["skipped_dedup"] += 1
                    continue

                enriched = await self._enrich_and_filter_item(item)
                if enriched:
                    filtered.append(enriched)
                    stats["kept"] += 1
                else:
                    stats["failed_quality_filter"] += 1
                if len(filtered) >= max_results:
                    break

            if len(filtered) >= max_results:
                break

        self.logger.info(
            "Trakt list fetch stats (target=%d, dedup=%s): pages=%d, raw=%d, "
            "duplicate=%d, missing_tmdb=%d, skipped_dedup=%d, "
            "failed_quality_filter=%d, kept=%d",
            max_results,
            dedup_mode,
            stats["pages_fetched"],
            stats["raw_items"],
            stats["duplicate_items"],
            stats["missing_tmdb_id"],
            stats["skipped_dedup"],
            stats["failed_quality_filter"],
            stats["kept"],
        )
        return filtered[:max_results]

    async def filter_and_request(
        self,
        results: List[Dict[str, Any]],
        dry_run: bool = False,
    ):
        """Filter list content and request via Seer."""
        requested_count = 0
        dry_run_items: Optional[List[Dict[str, Any]]] = [] if dry_run else None
        dedup_mode = str(self.job_data.get("filters", {}).get("dedup_mode") or "global").strip()
        per_list_seen = (
            self.db_manager.get_trakt_list_seen(self.job_id)
            if dedup_mode == "per_list"
            else set()
        )
        seen_to_record: List[Tuple[str, str]] = []

        for item in results:
            media_type = item.get("media_type") or self.job_data.get("media_type", "movie")
            tmdb_id = item["id"]
            title = item.get("title") or item.get("name") or "Unknown"
            seen_key = (str(tmdb_id), media_type)

            try:
                if dedup_mode == "per_list":
                    if seen_key in per_list_seen:
                        continue
                elif await self._should_skip_global_request(media_type, tmdb_id):
                    continue

                if dry_run:
                    dry_run_items.append(self._format_dry_run_item(media_type, item))
                    requested_count += 1
                    if dedup_mode == "per_list":
                        seen_to_record.append(seen_key)
                    continue

                success = await self.seer_client.request_media(
                    media_type,
                    item,
                    source={"id": TRAKT_LIST_SOURCE},
                    user=None,
                )
                if success:
                    requested_count += 1
                if dedup_mode == "per_list":
                    seen_to_record.append(seen_key)
            except Exception as exc:
                self.logger.error("Error processing %s: %s", title, exc)
                continue

        if dedup_mode == "per_list" and seen_to_record and not dry_run:
            self.db_manager.mark_trakt_list_seen(self.job_id, seen_to_record)

        return requested_count, dry_run_items


async def execute_trakt_list_job(job_id: int) -> ExecutionResult:
    """Execute a trakt_list job by ID."""
    logger = LoggerManager.get_logger("TraktListJobExecutor")
    logger.info("Starting execution of trakt list job: %s", job_id)

    try:
        automation = await TraktListAutomation.create(job_id)
        return await automation.run()
    except Exception as exc:
        logger.error("Failed to execute job %s: %s", job_id, exc)
        logger.error("Traceback: %s", traceback.format_exc())
        return ExecutionResult(
            success=False,
            results_count=0,
            requested_count=0,
            error_message=str(exc),
        )
