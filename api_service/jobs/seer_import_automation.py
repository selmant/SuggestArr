"""Seer request import automation: add Seer request media into SuggestArr DB.

Imports all Seer request statuses for media not yet tracked in SuggestArr.
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
from api_service.services.seer.seer_status import derive_seer_status, parse_seer_timestamp

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
        candidates.append({
            "tmdb_id": str(tmdb_id),
            "media_type": str(media_type),
            "title": primary.get("title") or f"tmdb:{tmdb_id}",
            "seer_status": seer_status,
            "requested_at": min(timestamps) if timestamps else None,
            "seer_request_count": len(entries),
        })
    return candidates


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

    would_import = imported = skipped = metadata_fallback = errors = 0

    try:
        index = await seer_client.get_requests_index()
        existing_keys = db.get_existing_request_keys()
        candidates = _collect_import_candidates(index)
        logger.info(
            "Seer request import: %d unique media key(s), %d already in SuggestArr (dry_run=%s).",
            len(candidates),
            len(existing_keys),
            dry_run,
        )

        for candidate in candidates:
            key: Tuple[str, str] = (candidate["media_type"], candidate["tmdb_id"])
            title = candidate["title"]
            seer_status = candidate["seer_status"]
            reason = (
                f"Imported from Seer ({seer_status}, {candidate['seer_request_count']} request record(s))."
            )

            if key in existing_keys:
                skipped += 1
                continue

            if dry_run:
                would_import += 1
                db.add_seer_import_log(
                    tmdb_id=candidate["tmdb_id"],
                    media_type=candidate["media_type"],
                    title=title,
                    action="would_import",
                    was_dry_run=True,
                    reason=reason,
                )
                continue

            try:
                used_fallback = not await _ensure_metadata(
                    seer_client,
                    db,
                    candidate["tmdb_id"],
                    candidate["media_type"],
                    title,
                )
                if used_fallback:
                    metadata_fallback += 1

                db.save_request(
                    candidate["media_type"],
                    candidate["tmdb_id"],
                    SEER_IMPORT_SOURCE,
                    source_origin=SEER_IMPORT_SOURCE,
                    rationale=reason,
                    requested_at=candidate.get("requested_at"),
                )
                existing_keys.add(key)
                imported += 1
                db.add_seer_import_log(
                    tmdb_id=candidate["tmdb_id"],
                    media_type=candidate["media_type"],
                    title=title,
                    action="imported",
                    was_dry_run=False,
                    reason=reason,
                )
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

    summary = (
        f"candidates={len(candidates)} "
        f"{'would_import' if dry_run else 'imported'}={would_import if dry_run else imported} "
        f"skipped_existing={skipped} metadata_fallback={metadata_fallback} errors={errors}"
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
        "imported": imported,
        "skipped": skipped,
        "metadata_fallback": metadata_fallback,
        "errors": errors,
    }
