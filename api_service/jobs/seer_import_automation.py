"""Seer request import automation: add Seer request media into SuggestArr DB.

Imports all Seer request statuses for media not yet tracked in SuggestArr.
Legacy rows with ``requested_by = 'Seer'`` are adopted into the Requests UI.
After import, existing approve/decline actions sync back to Seer by tmdb_id.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from api_service.config.logger_manager import LoggerManager
from api_service.db.database_manager import DatabaseManager
from api_service.services.config_service import ConfigService
from api_service.services.request_sources import SEER_IMPORT_SOURCE
from api_service.services.seer.request_actions import invalidate_requests_index_cache
from api_service.services.seer.seer_client import SeerClient
from api_service.services.seer.seer_status import derive_seer_status, is_pending_status, parse_seer_timestamp

_run_lock = threading.Lock()


def _format_utc_timestamp(dt: datetime) -> str:
    """Return UTC timestamp text compatible with SQL CURRENT_TIMESTAMP."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _utcnow_for_db() -> str:
    return _format_utc_timestamp(datetime.utcnow())


def _format_requested_at(value: Any) -> Optional[str]:
    parsed = parse_seer_timestamp(value)
    if parsed is None:
        return None
    return _format_utc_timestamp(parsed)


def _collect_import_candidates(index: Dict) -> List[Dict[str, Any]]:
    """Build one import candidate per unique Seer media key."""
    candidates: List[Dict[str, Any]] = []
    for (media_type, tmdb_id), entries in (index or {}).items():
        if not entries:
            continue

        timestamps = []
        for entry in entries:
            for field in ("created_at", "updated_at"):
                formatted = _format_requested_at(entry.get(field))
                if formatted:
                    timestamps.append(formatted)

        primary = entries[-1]
        seer_status = derive_seer_status(primary.get("status"), primary.get("media_status"))
        seer_updated_at = _format_requested_at(primary.get("updated_at")) or _format_requested_at(primary.get("created_at"))
        candidates.append({
            "tmdb_id": str(tmdb_id),
            "media_type": str(media_type),
            "title": primary.get("title") or f"tmdb:{tmdb_id}",
            "seer_request_id": primary.get("id"),
            "seer_request_status": primary.get("status"),
            "seer_media_status": primary.get("media_status"),
            "seer_status": seer_status,
            "seer_updated_at": seer_updated_at,
            "requested_at": min(timestamps) if timestamps else None,
            "seer_request_count": len(entries),
        })
    return candidates


def _matches_status_filter(candidate: Dict[str, Any], status_filter: str) -> bool:
    if status_filter == "pending":
        return is_pending_status(candidate.get("seer_request_status"))
    return True


def _refresh_seer_state(db: DatabaseManager, candidate: Dict[str, Any]) -> None:
    db.update_request_seer_state(
        candidate["tmdb_id"],
        candidate["media_type"],
        seer_request_id=candidate.get("seer_request_id"),
        seer_request_status=candidate.get("seer_request_status"),
        seer_media_status=candidate.get("seer_media_status"),
        seer_status=candidate.get("seer_status"),
        seer_updated_at=candidate.get("seer_updated_at"),
    )


async def _ensure_metadata(
    client: SeerClient,
    db: DatabaseManager,
    tmdb_id: str,
    media_type: str,
    fallback_title: str,
) -> bool:
    """Ensure metadata exists for an imported request item."""
    details = await client.get_media_details(tmdb_id, media_type)
    if details:
        media = {**details, "id": str(details.get("tmdb_id") or tmdb_id)}
        db.save_metadata(media, media_type)
        return True

    db.save_metadata({"id": str(tmdb_id), "title": fallback_title}, media_type)
    return False


async def _apply_candidate(
    *,
    db: DatabaseManager,
    client: SeerClient,
    candidate: Dict[str, Any],
    dry_run: bool,
    action_prefix: str,
) -> Tuple[str, bool]:
    """Import or adopt one candidate. Returns action name and metadata fallback flag."""
    title = candidate["title"]
    seer_status = candidate["seer_status"]
    reason = (
        f"{action_prefix} from Seer ({seer_status}, "
        f"{candidate['seer_request_count']} request record(s))."
    )

    if dry_run:
        db.add_seer_import_log(
            tmdb_id=candidate["tmdb_id"],
            media_type=candidate["media_type"],
            title=title,
            action=f"would_{action_prefix.lower()}",
            was_dry_run=True,
            reason=reason,
        )
        return f"would_{action_prefix.lower()}", False

    used_fallback = not await _ensure_metadata(
        client,
        db,
        candidate["tmdb_id"],
        candidate["media_type"],
        title,
    )

    if action_prefix == "Adopted":
        db.adopt_legacy_seer_request_row(
            candidate["tmdb_id"],
            candidate["media_type"],
            rationale=reason,
            requested_at=candidate.get("requested_at"),
            source=SEER_IMPORT_SOURCE,
        )
        action = "adopted"
    else:
        db.save_request(
            candidate["media_type"],
            candidate["tmdb_id"],
            SEER_IMPORT_SOURCE,
            source_origin=SEER_IMPORT_SOURCE,
            rationale=reason,
            requested_at=candidate.get("requested_at"),
        )
        action = "imported"

    db.add_seer_import_log(
        tmdb_id=candidate["tmdb_id"],
        media_type=candidate["media_type"],
        title=title,
        action=action,
        was_dry_run=False,
        reason=reason,
    )
    return action, used_fallback


async def execute_seer_import_job(
    force_run: bool = False,
    override_dry_run: Optional[bool] = None,
) -> Dict[str, Any]:
    """Import Seer requests missing from SuggestArr.

    :param force_run: If True, bypass the enabled gate (used by manual runs).
    :param override_dry_run: If set, override configured dry_run for this run only.
    :return: Summary dict.
    """
    logger = LoggerManager.get_logger("SeerRequestImport")
    db = DatabaseManager()
    settings = db.get_seer_import_settings()
    enabled = settings.get("enabled")
    dry_run = settings.get("dry_run") if override_dry_run is None else bool(override_dry_run)
    status_filter = settings.get("status_filter") or "all"

    if not enabled and not force_run:
        logger.debug("Seer request import disabled; skipping.")
        return {"status": "skipped", "message": "Seer request import is disabled."}

    env_vars = ConfigService.get_runtime_config()
    if not env_vars.get("SEER_API_URL") or not env_vars.get("SEER_TOKEN"):
        msg = "Seer is not configured (SEER_API_URL / SEER_TOKEN missing)."
        logger.warning(msg)
        db.update_seer_import_settings(
            last_run_at=_utcnow_for_db(),
            last_run_status="not_configured",
            last_run_summary=msg,
        )
        return {"status": "not_configured", "message": msg}

    seer_client = SeerClient(
        env_vars["SEER_API_URL"],
        env_vars["SEER_TOKEN"],
        env_vars.get("SEER_USER_NAME"),
        env_vars.get("SEER_USER_PSW"),
        env_vars.get("SEER_SESSION_TOKEN"),
        "all",
        False,
        False,
        {},
        False,
    )

    would_import = would_adopt = imported = adopted = refreshed = skipped = filtered = metadata_fallback = errors = 0

    try:
        index = await seer_client.get_requests_index()
        suggestarr_keys = db.get_suggestarr_request_keys()
        legacy_seer_keys = db.get_legacy_seer_request_keys()
        candidates = _collect_import_candidates(index)
        logger.info(
            "Seer request import: %d unique media key(s), %d in Requests UI, "
            "%d legacy Seer rows (dry_run=%s, status_filter=%s).",
            len(candidates),
            len(suggestarr_keys),
            len(legacy_seer_keys),
            dry_run,
            status_filter,
        )

        for candidate in candidates:
            key: Tuple[str, str] = (candidate["media_type"], candidate["tmdb_id"])
            title = candidate["title"]

            if key in suggestarr_keys:
                if not dry_run:
                    _refresh_seer_state(db, candidate)
                    refreshed += 1
                else:
                    skipped += 1

            if not _matches_status_filter(candidate, status_filter):
                filtered += 1
                continue

            if key in suggestarr_keys:
                continue

            if key in legacy_seer_keys:
                action_prefix = "Adopted"
            else:
                action_prefix = "Imported"

            try:
                if dry_run:
                    action, used_fallback = await _apply_candidate(
                        db=db,
                        client=seer_client,
                        candidate=candidate,
                        dry_run=True,
                        action_prefix=action_prefix,
                    )
                    if action == "would_adopted":
                        would_adopt += 1
                    else:
                        would_import += 1
                    continue

                action, used_fallback = await _apply_candidate(
                    db=db,
                    client=seer_client,
                    candidate=candidate,
                    dry_run=False,
                    action_prefix=action_prefix,
                )
                if used_fallback:
                    metadata_fallback += 1
                if action == "adopted":
                    adopted += 1
                    legacy_seer_keys.discard(key)
                else:
                    imported += 1
                _refresh_seer_state(db, candidate)
                suggestarr_keys.add(key)
            except Exception as exc:
                errors += 1
                logger.error(
                    "Seer import failed for %s/%s: %s",
                    candidate["media_type"],
                    candidate["tmdb_id"],
                    exc,
                )
                db.add_seer_import_log(
                    tmdb_id=candidate["tmdb_id"],
                    media_type=candidate["media_type"],
                    title=title,
                    action="error",
                    was_dry_run=False,
                    reason=str(exc)[:500],
                )
    finally:
        try:
            await seer_client.close()
        except Exception:
            pass
        invalidate_requests_index_cache()

    if dry_run:
        changed = would_import + would_adopt
        summary = (
            f"candidates={len(candidates)} would_import={would_import} would_adopt={would_adopt} "
            f"filtered={filtered} skipped_existing={skipped} metadata_fallback=0 errors={errors}"
        )
    else:
        changed = imported + adopted + refreshed
        summary = (
            f"candidates={len(candidates)} imported={imported} adopted={adopted} refreshed={refreshed} "
            f"filtered={filtered} skipped_existing={skipped} metadata_fallback={metadata_fallback} errors={errors}"
        )

    db.update_seer_import_settings(
        last_run_at=_utcnow_for_db(),
        last_run_status=("dry_run" if dry_run else "ok"),
        last_run_summary=summary,
    )
    logger.info("Seer request import finished: %s", summary)
    return {
        "status": "ok",
        "summary": summary,
        "dry_run": dry_run,
        "would_import": would_import,
        "would_adopt": would_adopt,
        "imported": imported,
        "adopted": adopted,
        "refreshed": refreshed,
        "skipped": skipped,
        "filtered": filtered,
        "metadata_fallback": metadata_fallback,
        "errors": errors,
        "changed": changed,
    }
