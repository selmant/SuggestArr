from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from api_service.config.config import load_env_vars
from api_service.db.database_manager import DatabaseManager
from api_service.services.trakt.media_user_augmentor import TraktAccountResolver
from api_service.services.trakt.sync_cache import (
    get_cached_item_status,
    get_cached_item_statuses,
    invalidate_user_sync_cache,
)
from api_service.services.trakt.trakt_client import TraktClient

_VALID_MEDIA_TYPES = {"movie", "tv"}


def _normalize_media_type(media_type: str) -> str:
    normalized = str(media_type or "").lower()
    if normalized not in _VALID_MEDIA_TYPES:
        raise ValueError("media_type must be movie or tv")
    return normalized


def _rating_stars_to_trakt(rating_stars: Any) -> Optional[int]:
    if rating_stars is None or rating_stars == "":
        return None
    rating = float(rating_stars)
    if rating < 0.5 or rating > 5:
        raise ValueError("rating_stars must be between 0.5 and 5")
    return max(1, min(10, int(round(rating * 2))))


def _watched_at_value(watched_at: str) -> Optional[str]:
    if watched_at == "now":
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    if watched_at == "release":
        return None
    raise ValueError("watched_at must be now or release")


def _resolve_credentials(config: dict[str, Any]) -> tuple[str, str]:
    integrations = config.get("integrations") if isinstance(config.get("integrations"), dict) else {}
    trakt = integrations.get("trakt") if isinstance(integrations.get("trakt"), dict) else {}
    client_id = str(config.get("TRAKT_CLIENT_ID") or trakt.get("client_id") or "").strip()
    client_secret = str(config.get("TRAKT_CLIENT_SECRET") or trakt.get("client_secret") or "").strip()
    if not client_id or not client_secret:
        raise RuntimeError("Trakt app credentials are not configured")
    return client_id, client_secret


def _resolve_provider(config: dict[str, Any]) -> str:
    provider = str(config.get("SELECTED_SERVICE") or "").strip().lower()
    if provider not in {"jellyfin", "plex", "emby"}:
        raise ValueError("Configured media service is required for Trakt request actions")
    return provider


def _resolve_trakt_account(db: DatabaseManager, user_id: str, config: dict[str, Any]) -> dict[str, Any]:
    if not user_id:
        raise ValueError("user_id is required")
    provider = _resolve_provider(config)
    identity = db.get_media_user_identity(provider, str(user_id))
    resolved = TraktAccountResolver(db).resolve(identity["id"])
    if not resolved:
        raise ValueError("Trakt account not linked")
    return resolved


def _status_payload(
    tmdb_id: str,
    media_type: str,
    user_id: str,
    status: dict[str, Any],
) -> dict[str, Any]:
    rating = status.get("rating")
    payload = {
        "tmdb_id": str(tmdb_id),
        "media_type": media_type,
        "user_id": str(user_id),
    }
    if "watched" in status:
        payload["watched"] = bool(status["watched"])
    if "rating" in status:
        payload["rating"] = rating
        payload["rating_stars"] = (float(rating) / 2) if rating is not None else None
    return payload


def _create_client(db: DatabaseManager, user_id: str) -> TraktClient:
    config = load_env_vars()
    client_id, client_secret = _resolve_credentials(config)
    resolved = _resolve_trakt_account(db, user_id, config)
    return TraktClient(
        client_id,
        client_secret,
        access_token=resolved.get("access_token", ""),
        refresh_token=resolved.get("refresh_token", ""),
        expires_at=resolved.get("expires_at"),
        db=db,
        link_id=resolved["id"],
        token_source=resolved.get("token_source", "manual_oauth"),
    )


async def get_request_trakt_status(
    db: DatabaseManager,
    tmdb_id: str,
    media_type: str,
    user_id: str,
) -> dict[str, Any]:
    media_type = _normalize_media_type(media_type)
    async with _create_client(db, user_id) as client:
        status = await get_cached_item_status(client, user_id, media_type, str(tmdb_id))
    return _status_payload(
        tmdb_id,
        media_type,
        user_id,
        {
            "watched": status.get("watched"),
            "rating": status.get("rating"),
        },
    )


async def get_request_trakt_statuses_batch(
    db: DatabaseManager,
    user_id: str,
    items: list[dict[str, str]],
) -> dict[str, Any]:
    if not user_id:
        raise ValueError("user_id is required")
    if not items:
        return {"user_id": str(user_id), "statuses": []}

    normalized_items = []
    for item in items:
        media_type = _normalize_media_type(str(item.get("media_type") or ""))
        tmdb_id = str(item.get("tmdb_id") or item.get("request_id") or "")
        if not tmdb_id:
            raise ValueError("each item requires tmdb_id or request_id")
        normalized_items.append({"media_type": media_type, "tmdb_id": tmdb_id})

    async with _create_client(db, user_id) as client:
        statuses = await get_cached_item_statuses(client, user_id, normalized_items)
    return {"user_id": str(user_id), "statuses": statuses}


async def fresh_item_status(
    client: TraktClient,
    user_id: str,
    media_type: str,
    tmdb_id: str,
) -> dict[str, Any]:
    """Bypass cached sync lists and resolve the current Trakt state for one item."""
    invalidate_user_sync_cache(user_id)
    return await get_cached_item_status(client, user_id, media_type, str(tmdb_id))


async def mark_request_watched(
    db: DatabaseManager,
    tmdb_id: str,
    media_type: str,
    user_id: str,
    watched_at: str = "now",
    rating_stars: Any = None,
) -> dict[str, Any]:
    media_type = _normalize_media_type(media_type)
    rating = _rating_stars_to_trakt(rating_stars)
    async with _create_client(db, user_id) as client:
        current = await fresh_item_status(client, user_id, media_type, str(tmdb_id))
        if not current.get("watched"):
            await client.add_to_history(media_type, str(tmdb_id), _watched_at_value(watched_at))
        if rating is not None:
            await client.add_rating(media_type, str(tmdb_id), rating)
        final = await fresh_item_status(client, user_id, media_type, str(tmdb_id))
        if rating is not None and final.get("rating") is None:
            final["rating"] = rating
        final["watched"] = True
    return _status_payload(
        tmdb_id,
        media_type,
        user_id,
        {
            "watched": final.get("watched"),
            "rating": final.get("rating"),
        },
    )


async def set_request_rating(
    db: DatabaseManager,
    tmdb_id: str,
    media_type: str,
    user_id: str,
    rating_stars: Any,
) -> dict[str, Any]:
    media_type = _normalize_media_type(media_type)
    rating = _rating_stars_to_trakt(rating_stars)
    if rating is None:
        raise ValueError("rating_stars is required")
    async with _create_client(db, user_id) as client:
        await client.add_rating(media_type, str(tmdb_id), rating)
        final = await fresh_item_status(client, user_id, media_type, str(tmdb_id))
        if final.get("rating") is None:
            final["rating"] = rating
    return _status_payload(
        tmdb_id,
        media_type,
        user_id,
        {
            "watched": final.get("watched"),
            "rating": final.get("rating"),
        },
    )


async def unmark_request_watched(
    db: DatabaseManager,
    tmdb_id: str,
    media_type: str,
    user_id: str,
    remove_rating: bool = False,
) -> dict[str, Any]:
    media_type = _normalize_media_type(media_type)
    async with _create_client(db, user_id) as client:
        current = await fresh_item_status(client, user_id, media_type, str(tmdb_id))
        if current.get("watched"):
            await client.remove_from_history(media_type, str(tmdb_id))
        if remove_rating and current.get("rating") is not None:
            await client.remove_rating(media_type, str(tmdb_id))
        final = await fresh_item_status(client, user_id, media_type, str(tmdb_id))
        if remove_rating:
            final["rating"] = None
        final["watched"] = False
    return _status_payload(
        tmdb_id,
        media_type,
        user_id,
        {
            "watched": final.get("watched"),
            "rating": final.get("rating"),
        },
    )
