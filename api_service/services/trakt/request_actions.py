from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from api_service.config.config import load_env_vars
from api_service.db.database_manager import DatabaseManager
from api_service.services.trakt.media_user_augmentor import TraktAccountResolver
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
    return {
        "tmdb_id": str(tmdb_id),
        "media_type": media_type,
        "user_id": str(user_id),
        "watched": bool(status.get("watched")),
        "rating": rating,
        "rating_stars": (float(rating) / 2) if rating is not None else None,
    }


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
        status = await client.get_item_sync_status(media_type, str(tmdb_id))
    return _status_payload(tmdb_id, media_type, user_id, status)


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
        await client.add_to_history(media_type, str(tmdb_id), _watched_at_value(watched_at))
        if rating is not None:
            await client.add_rating(media_type, str(tmdb_id), rating)
        status = await client.get_item_sync_status(media_type, str(tmdb_id))
        if status.get("rating") is None and rating is not None:
            status["rating"] = rating
        status["watched"] = True
    return _status_payload(tmdb_id, media_type, user_id, status)


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
        status = await client.get_item_sync_status(media_type, str(tmdb_id))
        status["rating"] = rating
    return _status_payload(tmdb_id, media_type, user_id, status)


async def unmark_request_watched(
    db: DatabaseManager,
    tmdb_id: str,
    media_type: str,
    user_id: str,
    remove_rating: bool = False,
) -> dict[str, Any]:
    media_type = _normalize_media_type(media_type)
    async with _create_client(db, user_id) as client:
        await client.remove_from_history(media_type, str(tmdb_id))
        if remove_rating:
            await client.remove_rating(media_type, str(tmdb_id))
        status = await client.get_item_sync_status(media_type, str(tmdb_id))
        status["watched"] = False
        if remove_rating:
            status["rating"] = None
    return _status_payload(tmdb_id, media_type, user_id, status)
