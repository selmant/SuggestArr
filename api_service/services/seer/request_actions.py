from __future__ import annotations

import time
from typing import Any, Optional

from api_service.config.config import load_env_vars
from api_service.db.database_manager import DatabaseManager
from api_service.services.seer.seer_client import PENDING_REQUEST_STATUSES, SeerClient

_VALID_MEDIA_TYPES = {"movie", "tv"}
_INDEX_CACHE_TTL_SECONDS = 5.0
_index_cache: dict[str, Any] = {"fetched_at": 0.0, "index": {}}


def _normalize_media_type(media_type: str) -> str:
    normalized = str(media_type or "").lower()
    if normalized not in _VALID_MEDIA_TYPES:
        raise ValueError("media_type must be movie or tv")
    return normalized


def _resolve_seer_credentials(config: dict[str, Any]) -> tuple[str, str, Optional[str]]:
    integrations = config.get("integrations") if isinstance(config.get("integrations"), dict) else {}
    seer = integrations.get("seer") if isinstance(integrations.get("seer"), dict) else {}
    api_url = str(config.get("SEER_API_URL") or seer.get("api_url") or "").strip()
    api_key = str(config.get("SEER_TOKEN") or seer.get("api_key") or "").strip()
    session_token = config.get("SEER_SESSION_TOKEN") or seer.get("session_token")
    if not api_url or not api_key:
        raise RuntimeError("Seer API URL and token are not configured")
    return api_url, api_key, session_token


def _create_client() -> SeerClient:
    config = load_env_vars()
    api_url, api_key, session_token = _resolve_seer_credentials(config)
    return SeerClient(api_url=api_url, api_key=api_key, session_token=session_token)


def invalidate_requests_index_cache() -> None:
    """Clear the in-process Seer requests index cache."""
    _index_cache["fetched_at"] = 0.0
    _index_cache["index"] = {}


async def _get_requests_index(client: SeerClient, *, force: bool = False) -> dict:
    now = time.monotonic()
    if (
        not force
        and _index_cache["index"]
        and (now - float(_index_cache["fetched_at"])) < _INDEX_CACHE_TTL_SECONDS
    ):
        return _index_cache["index"]

    index = await client.get_requests_index()
    _index_cache["fetched_at"] = now
    _index_cache["index"] = index
    return index


def _is_pending_status(status: Any) -> bool:
    return status in PENDING_REQUEST_STATUSES


def _derive_seer_status(request_status: Any, media_status: Any) -> str:
    if _is_pending_status(request_status):
        return "pending"
    if request_status in {3, "3", "declined", "DECLINED"}:
        return "declined"
    if media_status in {5, "5", "available", "AVAILABLE"}:
        return "available"
    if media_status in {4, "4", "partially_available", "PARTIALLY_AVAILABLE"}:
        return "partially_available"
    if media_status in {3, "3", "processing", "PROCESSING"}:
        return "processing"
    if request_status in {2, "2", "approved", "APPROVED"}:
        return "approved"
    return "not_found"


def _pick_primary_entry(entries: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not entries:
        return None
    pending = [entry for entry in entries if _is_pending_status(entry.get("status"))]
    if pending:
        return pending[-1]
    return entries[-1]


def _status_payload(
    tmdb_id: str,
    media_type: str,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    primary = _pick_primary_entry(entries)
    if not primary:
        return {
            "tmdb_id": str(tmdb_id),
            "media_type": media_type,
            "seer_status": "not_found",
            "seer_request_ids": [],
            "can_action": False,
        }

    pending_ids = [
        int(entry["id"])
        for entry in entries
        if entry.get("id") is not None and _is_pending_status(entry.get("status"))
    ]
    seer_status = _derive_seer_status(primary.get("status"), primary.get("media_status"))
    return {
        "tmdb_id": str(tmdb_id),
        "media_type": media_type,
        "seer_status": seer_status,
        "seer_request_ids": pending_ids or [int(primary["id"])] if primary.get("id") is not None else [],
        "can_action": bool(pending_ids),
    }


def _lookup_entries(index: dict, media_type: str, tmdb_id: str) -> list[dict[str, Any]]:
    return list(index.get((media_type, str(tmdb_id)), []))


async def get_request_seer_status(
    db: DatabaseManager,
    tmdb_id: str,
    media_type: str,
) -> dict[str, Any]:
    """Return Seer approval status for a SuggestArr request item."""
    media_type = _normalize_media_type(media_type)
    async with _create_client() as client:
        index = await _get_requests_index(client)
    entries = _lookup_entries(index, media_type, str(tmdb_id))
    return _status_payload(tmdb_id, media_type, entries)


async def get_request_seer_statuses_batch(
    db: DatabaseManager,
    items: list[dict[str, str]],
) -> dict[str, Any]:
    """Return Seer approval status for many request items in one index fetch."""
    if not items:
        return {"statuses": []}

    normalized_items = []
    for item in items:
        media_type = _normalize_media_type(str(item.get("media_type") or ""))
        tmdb_id = str(item.get("tmdb_id") or item.get("request_id") or "")
        if not tmdb_id:
            raise ValueError("each item requires tmdb_id or request_id")
        normalized_items.append({"media_type": media_type, "tmdb_id": tmdb_id})

    async with _create_client() as client:
        index = await _get_requests_index(client)

    statuses = [
        _status_payload(item["tmdb_id"], item["media_type"], _lookup_entries(index, item["media_type"], item["tmdb_id"]))
        for item in normalized_items
    ]
    return {"statuses": statuses}


async def _apply_action(
    db: DatabaseManager,
    tmdb_id: str,
    media_type: str,
    action: str,
) -> dict[str, Any]:
    media_type = _normalize_media_type(media_type)
    invalidate_requests_index_cache()

    async with _create_client() as client:
        index = await _get_requests_index(client, force=True)
        entries = _lookup_entries(index, media_type, str(tmdb_id))
        pending_ids = [
            int(entry["id"])
            for entry in entries
            if entry.get("id") is not None and _is_pending_status(entry.get("status"))
        ]
        if not pending_ids:
            return _status_payload(tmdb_id, media_type, entries)

        for request_id in pending_ids:
            success = (
                await client.approve_request(request_id)
                if action == "approve"
                else await client.decline_request(request_id)
            )
            if not success:
                raise RuntimeError(f"Seer could not {action} request {request_id}")

        invalidate_requests_index_cache()
        index = await _get_requests_index(client, force=True)
        entries = _lookup_entries(index, media_type, str(tmdb_id))
        return _status_payload(tmdb_id, media_type, entries)


async def approve_request(
    db: DatabaseManager,
    tmdb_id: str,
    media_type: str,
) -> dict[str, Any]:
    """Approve pending Seer request(s) matching a SuggestArr request item."""
    return await _apply_action(db, tmdb_id, media_type, "approve")


async def decline_request(
    db: DatabaseManager,
    tmdb_id: str,
    media_type: str,
) -> dict[str, Any]:
    """Decline pending Seer request(s) matching a SuggestArr request item."""
    return await _apply_action(db, tmdb_id, media_type, "decline")
