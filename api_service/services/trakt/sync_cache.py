from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

from api_service.services.trakt.trakt_client import TraktClient

_DEFAULT_TTL_SECONDS = 7200


def _cache_ttl_seconds() -> int:
    raw = os.getenv("TRAKT_SYNC_CACHE_TTL_SECONDS", str(_DEFAULT_TTL_SECONDS))
    try:
        return max(30, int(raw))
    except ValueError:
        return _DEFAULT_TTL_SECONDS


@dataclass
class _UserSyncSnapshot:
    watched_movies: list[dict[str, Any]]
    watched_shows: list[dict[str, Any]]
    ratings_movies: list[dict[str, Any]]
    ratings_shows: list[dict[str, Any]]
    fetched_at: float

    def expired(self, ttl_seconds: int) -> bool:
        return (time.time() - self.fetched_at) > ttl_seconds


_CACHE: dict[str, _UserSyncSnapshot] = {}
_CACHE_LOCKS: dict[str, asyncio.Lock] = {}


def invalidate_user_sync_cache(user_id: str) -> None:
    """Drop cached Trakt sync lists for a media user."""
    _CACHE.pop(str(user_id), None)


def clear_sync_cache() -> None:
    """Clear all cached Trakt sync snapshots (tests)."""
    _CACHE.clear()


def _lock_for_user(user_id: str) -> asyncio.Lock:
    key = str(user_id)
    if key not in _CACHE_LOCKS:
        _CACHE_LOCKS[key] = asyncio.Lock()
    return _CACHE_LOCKS[key]


async def warm_user_sync_cache(client: TraktClient, user_id: str) -> _UserSyncSnapshot:
    """Ensure Trakt watched/ratings lists are cached for the given media user."""
    user_id = str(user_id)
    ttl_seconds = _cache_ttl_seconds()
    snapshot = _CACHE.get(user_id)
    if snapshot and not snapshot.expired(ttl_seconds):
        return snapshot

    lock = _lock_for_user(user_id)
    async with lock:
        snapshot = _CACHE.get(user_id)
        if snapshot and not snapshot.expired(ttl_seconds):
            return snapshot

        watched_movies, watched_shows, ratings_movies, ratings_shows = await asyncio.gather(
            client._request("GET", "/sync/watched/movies", authenticated=True),
            client._request("GET", "/sync/watched/shows", authenticated=True),
            client._request("GET", "/sync/ratings/movies", authenticated=True),
            client._request("GET", "/sync/ratings/shows", authenticated=True),
        )
        snapshot = _UserSyncSnapshot(
            watched_movies=watched_movies or [],
            watched_shows=watched_shows or [],
            ratings_movies=ratings_movies or [],
            ratings_shows=ratings_shows or [],
            fetched_at=time.time(),
        )
        _CACHE[user_id] = snapshot
        return snapshot


def lookup_item_status(
    snapshot: _UserSyncSnapshot,
    media_type: str,
    tmdb_id: str,
) -> dict[str, Any]:
    """Resolve watched/rating for one item from a warmed sync snapshot."""
    tmdb_id = str(tmdb_id)
    if media_type == "movie":
        watched = TraktClient._payload_contains_tmdb(snapshot.watched_movies, "movie", tmdb_id)
        rating = TraktClient._find_rating_for_tmdb(snapshot.ratings_movies, "movie", tmdb_id)
    elif media_type == "tv":
        watched = TraktClient._payload_contains_tmdb(snapshot.watched_shows, "show", tmdb_id)
        rating = TraktClient._find_rating_for_tmdb(snapshot.ratings_shows, "show", tmdb_id)
    else:
        raise ValueError("media_type must be movie or tv")
    return {"watched": watched, "rating": rating}


async def get_cached_item_status(
    client: TraktClient,
    user_id: str,
    media_type: str,
    tmdb_id: str,
) -> dict[str, Any]:
    """Return watched/rating using a per-user sync list cache."""
    snapshot = await warm_user_sync_cache(client, user_id)
    return lookup_item_status(snapshot, media_type, str(tmdb_id))


async def get_cached_item_statuses(
    client: TraktClient,
    user_id: str,
    items: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Return watched/rating for many items after at most one sync refresh."""
    snapshot = await warm_user_sync_cache(client, user_id)
    results: list[dict[str, Any]] = []
    for item in items:
        media_type = str(item.get("media_type") or "")
        tmdb_id = str(item.get("tmdb_id") or "")
        status = lookup_item_status(snapshot, media_type, tmdb_id)
        results.append({
            "tmdb_id": tmdb_id,
            "media_type": media_type,
            "user_id": str(user_id),
            "watched": bool(status.get("watched")),
            "rating": status.get("rating"),
            "rating_stars": (float(status["rating"]) / 2) if status.get("rating") is not None else None,
        })
    return results
