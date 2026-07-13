from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Optional

from api_service.config.config import load_env_vars
from api_service.db.database_manager import DatabaseManager
from api_service.services.seer.seer_client import SeerClient
from api_service.services.seer.seer_status import (
    derive_seer_status,
    is_pending_status,
    parse_seer_timestamp,
)

_VALID_MEDIA_TYPES = {"movie", "tv"}
_INDEX_CACHE_TTL_SECONDS = 5.0
_DETAILS_CACHE_TTL_SECONDS = 600.0
_index_cache: dict[str, Any] = {"fetched_at": 0.0, "index": {}}
_details_cache: dict[tuple[str, str], dict[str, Any]] = {}


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


def invalidate_request_details_cache() -> None:
    """Clear the in-process Seer request details cache."""
    _details_cache.clear()


def _get_cached_request_details(media_type: str, tmdb_id: str) -> Optional[dict[str, Any]]:
    cache_key = (media_type, str(tmdb_id))
    entry = _details_cache.get(cache_key)
    if not entry:
        return None
    if (time.monotonic() - float(entry["fetched_at"])) >= _DETAILS_CACHE_TTL_SECONDS:
        _details_cache.pop(cache_key, None)
        return None
    return entry["details"]


def _set_cached_request_details(media_type: str, tmdb_id: str, details: dict[str, Any]) -> None:
    _details_cache[(media_type, str(tmdb_id))] = {
        "fetched_at": time.monotonic(),
        "details": details,
    }


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


def _format_utc_timestamp(dt: datetime) -> str:
    """Return UTC timestamp text compatible with SQL CURRENT_TIMESTAMP."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _utcnow_for_db() -> str:
    return _format_utc_timestamp(datetime.utcnow())


def _format_seer_updated_at(entry: dict[str, Any]) -> Optional[str]:
    """Return a DB-friendly Seer updated timestamp from a request entry."""
    for field in ("updated_at", "created_at"):
        parsed = parse_seer_timestamp(entry.get(field))
        if parsed is not None:
            return _format_utc_timestamp(parsed)
    return None


def _persist_seer_state(
    db: DatabaseManager,
    tmdb_id: str,
    media_type: str,
    entries: list[dict[str, Any]],
) -> None:
    """Persist the latest Seer status snapshot onto matching SuggestArr rows."""
    primary = _pick_primary_entry(entries)
    if not primary:
        db.update_request_seer_state(
            tmdb_id,
            media_type,
            seer_request_id=None,
            seer_request_status=None,
            seer_media_status=None,
            seer_status="not_found",
            seer_updated_at=_utcnow_for_db(),
        )
        return

    db.update_request_seer_state(
        tmdb_id,
        media_type,
        seer_request_id=primary.get("id"),
        seer_request_status=primary.get("status"),
        seer_media_status=primary.get("media_status"),
        seer_status=derive_seer_status(primary.get("status"), primary.get("media_status")),
        seer_updated_at=_format_seer_updated_at(primary) or _utcnow_for_db(),
    )


def _pick_primary_entry(entries: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not entries:
        return None
    pending = [entry for entry in entries if is_pending_status(entry.get("status"))]
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
        if entry.get("id") is not None and is_pending_status(entry.get("status"))
    ]
    seer_status = derive_seer_status(primary.get("status"), primary.get("media_status"))
    return {
        "tmdb_id": str(tmdb_id),
        "media_type": media_type,
        "seer_status": seer_status,
        "seer_request_ids": pending_ids or [int(primary["id"])] if primary.get("id") is not None else [],
        "can_action": bool(pending_ids),
    }


def _lookup_entries(index: dict, media_type: str, tmdb_id: str) -> list[dict[str, Any]]:
    return list(index.get((media_type, str(tmdb_id)), []))


async def get_request_details(
    db: DatabaseManager,
    tmdb_id: str,
    media_type: str,
) -> dict[str, Any]:
    """Return rich Seer-backed metadata for a SuggestArr request item."""
    media_type = _normalize_media_type(media_type)
    tmdb_id = str(tmdb_id)
    cached = _get_cached_request_details(media_type, tmdb_id)
    if cached is not None:
        return cached

    async with _create_client() as client:
        details = await client.get_media_details(tmdb_id, media_type)
    if not details:
        return {
            "available": False,
            "tmdb_id": tmdb_id,
            "media_type": media_type,
        }
    _set_cached_request_details(media_type, tmdb_id, details)
    return details


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
    _persist_seer_state(db, tmdb_id, media_type, entries)
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

    statuses = []
    for item in normalized_items:
        entries = _lookup_entries(index, item["media_type"], item["tmdb_id"])
        _persist_seer_state(db, item["tmdb_id"], item["media_type"], entries)
        statuses.append(_status_payload(item["tmdb_id"], item["media_type"], entries))
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
            if entry.get("id") is not None and is_pending_status(entry.get("status"))
        ]
        if not pending_ids:
            _persist_seer_state(db, tmdb_id, media_type, entries)
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
        # Seer can briefly return the old pending state immediately after a
        # successful decline. Treat the accepted action as authoritative so
        # callers do not resurrect the item while Seer propagates the change.
        if action == "decline" and any(is_pending_status(entry.get("status")) for entry in entries):
            entries = [
                {**entry, "status": 3} if is_pending_status(entry.get("status")) else entry
                for entry in entries
            ]
        _persist_seer_state(db, tmdb_id, media_type, entries)
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
