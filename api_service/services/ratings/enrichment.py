"""Fetch and cache multi-source ratings for metadata rows."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from api_service.config.config import load_env_vars
from api_service.config.logger_manager import LoggerManager

logger = LoggerManager.get_logger(__name__)

_DEFAULT_TTL_HOURS = 168


@dataclass
class _RunRatingsSnapshot:
    ratings: dict[str, Any]
    fetched_at: float

    def expired(self, ttl_seconds: int) -> bool:
        return (time.time() - self.fetched_at) > ttl_seconds


_RUN_CACHE: dict[str, _RunRatingsSnapshot] = {}
_RUN_CACHE_LOCKS: dict[str, asyncio.Lock] = {}


def clear_run_ratings_cache() -> None:
    """Clear in-run ratings cache (tests)."""
    _RUN_CACHE.clear()


def invalidate_run_ratings_cache(media_id: str, media_type: str) -> None:
    """Drop a single in-run cache entry."""
    _RUN_CACHE.pop(_cache_key(media_id, media_type), None)


def _cache_key(media_id: str, media_type: str) -> str:
    return f"{media_type}:{media_id}"


def _lock_for_key(cache_key: str) -> asyncio.Lock:
    if cache_key not in _RUN_CACHE_LOCKS:
        _RUN_CACHE_LOCKS[cache_key] = asyncio.Lock()
    return _RUN_CACHE_LOCKS[cache_key]


def _ratings_ttl_hours() -> int:
    config = load_env_vars()
    try:
        return max(1, int(config.get('RATINGS_CACHE_TTL_HOURS', _DEFAULT_TTL_HOURS)))
    except (TypeError, ValueError):
        return _DEFAULT_TTL_HOURS


def _ratings_ttl_seconds() -> int:
    return _ratings_ttl_hours() * 3600


def _parse_db_timestamp(value: Any) -> Optional[datetime]:
    if value in (None, ''):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _db_cache_fresh(ratings_updated_at: Any) -> bool:
    parsed = _parse_db_timestamp(ratings_updated_at)
    if parsed is None:
        return False
    age_seconds = (datetime.now(timezone.utc) - parsed).total_seconds()
    return age_seconds < _ratings_ttl_seconds()


def _has_any_rating(ratings: dict[str, Any]) -> bool:
    return any(
        ratings.get(key) is not None
        for key in (
            'imdb_rating',
            'rt_rating',
            'rt_user_rating',
            'metacritic_rating',
            'trakt_rating',
        )
    )


def _apply_ratings_to_media(media: dict[str, Any], ratings: dict[str, Any]) -> None:
    for key in (
        'imdb_id',
        'imdb_rating',
        'imdb_votes',
        'rt_rating',
        'rt_user_rating',
        'metacritic_rating',
        'trakt_rating',
        'trakt_votes',
        'ratings_updated_at',
    ):
        if key in ratings:
            media[key] = ratings[key]
    # TMDb rating (vote_average) lives in the metadata.rating column; only fill
    # it when the media item is missing one so we never clobber a real value.
    if ratings.get('rating') is not None and media.get('rating') in (None, ''):
        media['rating'] = ratings['rating']


_OMDB_RATING_KEYS = ('imdb_rating', 'imdb_votes', 'rt_rating', 'rt_user_rating', 'metacritic_rating')


def _set_tmdb_rating(media: dict[str, Any], ratings: dict[str, Any], value: Any) -> None:
    """Fill the TMDb rating when the media item is missing one."""
    if value is not None and media.get('rating') in (None, ''):
        ratings['rating'] = value
        media['rating'] = value


async def _fetch_external_ratings(
    media: dict[str, Any],
    media_type: str,
    tmdb_client,
    trakt_client=None,
    mdblist_client=None,
) -> dict[str, Any]:
    media_id = str(media.get('id') or media.get('media_id') or '')
    title = media.get('title') or media.get('name')
    ratings: dict[str, Any] = {
        'imdb_id': media.get('imdb_id'),
        'imdb_rating': None,
        'imdb_votes': None,
        'rt_rating': None,
        'rt_user_rating': None,
        'metacritic_rating': None,
        'trakt_rating': None,
        'trakt_votes': None,
        'rating': None,
        'title': title,
    }

    # 1. MDBList (preferred): a single TMDb-id lookup aggregates IMDb / RT
    #    critic + audience / Metacritic / Trakt / TMDb for movies AND series.
    #    Unlike OMDb, its RT/Metacritic coverage for TV is reliable.
    if mdblist_client is not None and media_id:
        try:
            mdb = await mdblist_client.get_ratings(media_type, media_id)
        except Exception as exc:
            mdb = None
            logger.debug("MDBList lookup failed for %s %s: %s", media_type, media_id, exc)
        if mdb:
            if not ratings['imdb_id'] and mdb.get('imdb_id'):
                ratings['imdb_id'] = mdb['imdb_id']
            for key in ('imdb_rating', 'imdb_votes', 'rt_rating', 'rt_user_rating',
                        'metacritic_rating', 'trakt_rating', 'trakt_votes'):
                if mdb.get(key) is not None:
                    ratings[key] = mdb[key]
            _set_tmdb_rating(media, ratings, mdb.get('rating'))

    imdb_id = ratings['imdb_id']

    # 2. Resolve a missing IMDb id and/or TMDb rating from TMDb details.
    need_details = (
        tmdb_client is not None
        and media_id
        and (not imdb_id or media.get('rating') in (None, ''))
    )
    if need_details:
        details = await tmdb_client._get_item_details(int(media_id), media_type) or {}
        if not imdb_id:
            imdb_id = details.get('imdb_id')
            ratings['imdb_id'] = imdb_id
        _set_tmdb_rating(media, ratings, details.get('rating'))

    # 3. OMDb fallback for any IMDb/RT/Metacritic field MDBList did not supply.
    omdb_client = getattr(tmdb_client, 'omdb_client', None) if tmdb_client is not None else None
    if omdb_client and imdb_id and any(ratings.get(k) is None for k in _OMDB_RATING_KEYS):
        omdb_data = await omdb_client.get_rating(imdb_id, media_type)
        if omdb_data:
            for key in _OMDB_RATING_KEYS:
                if ratings.get(key) is None and omdb_data.get(key) is not None:
                    ratings[key] = omdb_data[key]

    # 4. Trakt fallback for the community rating.
    if trakt_client is not None and media_id and ratings.get('trakt_rating') is None:
        try:
            community = await trakt_client.get_community_rating(media_type, media_id)
            if community:
                ratings['trakt_rating'] = community.get('trakt_rating')
                ratings['trakt_votes'] = community.get('trakt_votes')
        except Exception as exc:
            logger.debug(
                "Trakt community rating lookup failed for %s %s: %s",
                media_type,
                media_id,
                exc,
            )

    if _has_any_rating(ratings):
        ratings['ratings_updated_at'] = datetime.now(timezone.utc)
    return ratings


async def enrich_media_ratings(
    media: dict[str, Any],
    media_type: str,
    tmdb_client=None,
    db_manager=None,
    trakt_client=None,
    force_refresh: bool = False,
    mdblist_client=None,
) -> dict[str, Any]:
    """Populate multi-source ratings on ``media`` using DB + in-run caches."""
    media_id = str(media.get('id') or media.get('media_id') or '')
    if not media_id:
        return media

    cache_key = _cache_key(media_id, media_type)
    ttl_seconds = _ratings_ttl_seconds()
    snapshot = _RUN_CACHE.get(cache_key)
    if not force_refresh and snapshot and not snapshot.expired(ttl_seconds):
        _apply_ratings_to_media(media, snapshot.ratings)
        return media

    if db_manager is not None and not force_refresh:
        stored = db_manager.get_metadata_ratings(media_id, media_type)
        if stored and _db_cache_fresh(stored.get('ratings_updated_at')):
            cached = {k: v for k, v in stored.items() if k != 'ratings_updated_at'}
            _RUN_CACHE[cache_key] = _RunRatingsSnapshot(cached, time.time())
            _apply_ratings_to_media(media, cached)
            return media

    lock = _lock_for_key(cache_key)
    async with lock:
        snapshot = _RUN_CACHE.get(cache_key)
        if not force_refresh and snapshot and not snapshot.expired(ttl_seconds):
            _apply_ratings_to_media(media, snapshot.ratings)
            return media

        if db_manager is not None and not force_refresh:
            stored = db_manager.get_metadata_ratings(media_id, media_type)
            if stored and _db_cache_fresh(stored.get('ratings_updated_at')):
                cached = {k: v for k, v in stored.items() if k != 'ratings_updated_at'}
                _RUN_CACHE[cache_key] = _RunRatingsSnapshot(cached, time.time())
                _apply_ratings_to_media(media, cached)
                return media

        ratings = await _fetch_external_ratings(
            media, media_type, tmdb_client, trakt_client, mdblist_client
        )
        # Persist a resolved TMDb rating independently: save_metadata uses
        # INSERT OR IGNORE (no-op for existing rows) and the backfill path never
        # calls it, so fill the metadata.rating column here when it is empty.
        if db_manager is not None and ratings.get('rating') is not None:
            try:
                db_manager.update_metadata_tmdb_rating(media_id, media_type, ratings['rating'])
            except Exception as exc:
                logger.debug("Failed to persist TMDb rating for %s %s: %s", media_type, media_id, exc)
        if _has_any_rating(ratings) and db_manager is not None:
            db_manager.update_metadata_ratings(media_id, media_type, ratings)
            cached = {k: v for k, v in ratings.items() if k != 'ratings_updated_at'}
            _RUN_CACHE[cache_key] = _RunRatingsSnapshot(cached, time.time())
            _apply_ratings_to_media(media, cached)
        elif _has_any_rating(ratings):
            cached = {k: v for k, v in ratings.items() if k != 'ratings_updated_at'}
            _RUN_CACHE[cache_key] = _RunRatingsSnapshot(cached, time.time())
            _apply_ratings_to_media(media, cached)

    return media


def build_enrichment_clients():
    """Create optional MDBList/TMDb/Trakt clients for rating enrichment.

    Each provider is built independently: a configured provider is usable even
    when the others are absent (e.g. Trakt community ratings or MDBList
    aggregated ratings work without a TMDb key).

    Returns:
        tuple: ``(tmdb_client, trakt_client, mdblist_client)`` with any element
        set to ``None`` when its API key is not configured.
    """
    from api_service.services.mdblist.mdblist_client import MdbListClient
    from api_service.services.omdb.omdb_client import OmdbClient
    from api_service.services.tmdb.tmdb_client import TMDbClient
    from api_service.services.trakt.trakt_client import TraktClient

    env = load_env_vars()

    tmdb_client = None
    tmdb_key = (env.get('TMDB_API_KEY') or '').strip()
    if tmdb_key:
        omdb_client = None
        omdb_key = (env.get('OMDB_API_KEY') or '').strip()
        if omdb_key:
            omdb_client = OmdbClient(omdb_key)

        tmdb_client = TMDbClient(
            api_key=tmdb_key,
            search_size=1,
            tmdb_threshold=None,
            tmdb_min_votes=None,
            include_no_ratings=True,
            filter_release_year=None,
            filter_language=None,
            filter_genre=None,
            filter_region_provider=None,
            filter_streaming_services=None,
            omdb_client=omdb_client,
        )

    mdblist_client = None
    mdblist_key = (env.get('MDBLIST_API_KEY') or '').strip()
    if mdblist_key:
        mdblist_client = MdbListClient(mdblist_key)

    trakt_client = None
    trakt_id = (env.get('TRAKT_CLIENT_ID') or '').strip()
    trakt_secret = (env.get('TRAKT_CLIENT_SECRET') or '').strip()
    if trakt_id:
        trakt_client = TraktClient(
            client_id=trakt_id,
            client_secret=trakt_secret,
            access_token=env.get('TRAKT_ACCESS_TOKEN') or '',
            refresh_token=env.get('TRAKT_REFRESH_TOKEN') or '',
            expires_at=env.get('TRAKT_EXPIRES_AT'),
        )

    return tmdb_client, trakt_client, mdblist_client


async def enrich_and_save_metadata(
    media: dict[str, Any],
    media_type: str,
    db_manager,
    tmdb_client=None,
    trakt_client=None,
    mdblist_client=None,
) -> dict[str, Any]:
    """Enrich ratings then persist metadata for a media dict."""
    if tmdb_client is None and trakt_client is None and mdblist_client is None:
        tmdb_client, trakt_client, mdblist_client = build_enrichment_clients()

    await enrich_media_ratings(
        media,
        media_type,
        tmdb_client=tmdb_client,
        db_manager=db_manager,
        trakt_client=trakt_client,
        mdblist_client=mdblist_client,
    )
    db_manager.save_metadata(media, media_type)
    return media
