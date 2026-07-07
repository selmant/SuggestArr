"""Seer request prune automation: delete old settled Seer request records.

Safe by default: disabled, dry-run on, never prunes pending/in-flight requests.
Optionally removes matching SuggestArr DB rows when sync_suggestarr is enabled.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from api_service.config.logger_manager import LoggerManager
from api_service.db.database_manager import DatabaseManager
from api_service.services.config_service import ConfigService
from api_service.services.seer.request_actions import invalidate_requests_index_cache
from api_service.services.seer.seer_client import SeerClient
from api_service.services.seer.seer_status import (
    classify_prune_bucket,
    derive_seer_status,
    parse_seer_timestamp,
)

_run_lock = threading.Lock()
DEFAULT_RETENTION = {
    "declined_days": 14,
    "failed_days": 7,
    "completed_days": 7,
    "deleted_days": 3,
}


def _format_utc_timestamp(dt: datetime) -> str:
    """Return UTC timestamp text compatible with SQL CURRENT_TIMESTAMP."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _utcnow_for_db() -> str:
    return _format_utc_timestamp(datetime.utcnow())


def _retention_days(settings: Dict[str, Any], bucket: str) -> int:
    key = f"{bucket}_days"
    try:
        return max(1, int(settings.get(key) or DEFAULT_RETENTION.get(key, 7)))
    except (TypeError, ValueError):
        return DEFAULT_RETENTION.get(key, 7)


def _flatten_requests_index(index: Dict) -> List[Dict[str, Any]]:
    """Expand a Seer requests index into flat request rows."""
    rows: List[Dict[str, Any]] = []
    for (media_type, tmdb_id), entries in (index or {}).items():
        for entry in entries or []:
            if entry.get("id") is None:
                continue
            rows.append({
                "seer_request_id": int(entry["id"]),
                "tmdb_id": str(tmdb_id),
                "media_type": str(media_type),
                "status": entry.get("status"),
                "media_status": entry.get("media_status"),
                "updated_at": entry.get("updated_at"),
                "title": entry.get("title") or f"tmdb:{tmdb_id}",
            })
    return rows


def _is_prune_candidate(row: Dict[str, Any], settings: Dict[str, Any], now: datetime) -> Optional[str]:
    """Return prune bucket when row is old enough, else None."""
    seer_status = derive_seer_status(row.get("status"), row.get("media_status"))
    bucket = classify_prune_bucket(seer_status)
    if not bucket:
        return None

    updated_at = parse_seer_timestamp(row.get("updated_at"))
    if updated_at is None:
        return None

    retention_days = _retention_days(settings, bucket)
    cutoff = now - timedelta(days=retention_days)
    if updated_at > cutoff:
        return None
    return bucket


async def execute_seer_request_prune_job(
    force_run: bool = False,
    override_dry_run: Optional[bool] = None,
) -> Dict[str, Any]:
    """Run the Seer request prune pass.

    :param force_run: If True, bypass the enabled gate (used by manual runs).
    :param override_dry_run: If set, override configured dry_run for this run only.
    :return: Summary dict.
    """
    logger = LoggerManager.get_logger("SeerRequestPrune")
    db = DatabaseManager()
    settings = db.get_seer_request_prune_settings()
    enabled = settings.get("enabled")
    dry_run = settings.get("dry_run") if override_dry_run is None else bool(override_dry_run)
    sync_suggestarr = bool(settings.get("sync_suggestarr"))

    if not enabled and not force_run:
        logger.debug("Seer request prune disabled; skipping.")
        return {"status": "skipped", "message": "Seer request prune is disabled."}

    env_vars = ConfigService.get_runtime_config()
    if not env_vars.get("SEER_API_URL") or not env_vars.get("SEER_TOKEN"):
        msg = "Seer is not configured (SEER_API_URL / SEER_TOKEN missing)."
        logger.warning(msg)
        db.update_seer_request_prune_settings(
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

    now = datetime.utcnow()
    would_delete = deleted = synced = skipped = errors = 0

    try:
        index = await seer_client.get_requests_index()
        rows = _flatten_requests_index(index)
        logger.info(
            "Seer request prune: scanning %d request(s) (dry_run=%s, sync_suggestarr=%s).",
            len(rows),
            dry_run,
            sync_suggestarr,
        )

        for row in rows:
            bucket = _is_prune_candidate(row, settings, now)
            if not bucket:
                skipped += 1
                continue

            retention_days = _retention_days(settings, bucket)
            reason = (
                f"Seer status bucket={bucket}, older than {retention_days} day(s) "
                f"(updated_at={row.get('updated_at')})."
            )

            if dry_run:
                would_delete += 1
                db.add_seer_request_prune_log(
                    seer_request_id=row["seer_request_id"],
                    tmdb_id=row["tmdb_id"],
                    media_type=row["media_type"],
                    title=row["title"],
                    action="would_delete",
                    was_dry_run=True,
                    reason=reason,
                )
                continue

            try:
                ok = await seer_client.delete_request(row["seer_request_id"])
                if not ok:
                    errors += 1
                    db.add_seer_request_prune_log(
                        seer_request_id=row["seer_request_id"],
                        tmdb_id=row["tmdb_id"],
                        media_type=row["media_type"],
                        title=row["title"],
                        action="delete_failed",
                        was_dry_run=False,
                        reason="Seer DELETE returned a non-success status; see logs.",
                    )
                    continue

                deleted += 1
                db.add_seer_request_prune_log(
                    seer_request_id=row["seer_request_id"],
                    tmdb_id=row["tmdb_id"],
                    media_type=row["media_type"],
                    title=row["title"],
                    action="deleted",
                    was_dry_run=False,
                    reason=reason,
                )

                if sync_suggestarr:
                    db.delete_request_row(row["tmdb_id"], row["media_type"])
                    synced += 1
                    db.add_seer_request_prune_log(
                        seer_request_id=row["seer_request_id"],
                        tmdb_id=row["tmdb_id"],
                        media_type=row["media_type"],
                        title=row["title"],
                        action="synced_suggestarr_row",
                        was_dry_run=False,
                        reason="Removed matching SuggestArr request row.",
                    )
            except Exception as exc:
                errors += 1
                logger.error(
                    "Seer request prune failed for request_id=%s: %s",
                    row["seer_request_id"],
                    exc,
                )
                db.add_seer_request_prune_log(
                    seer_request_id=row["seer_request_id"],
                    tmdb_id=row["tmdb_id"],
                    media_type=row["media_type"],
                    title=row["title"],
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
        f"scanned={len(rows)} "
        f"{'would_delete' if dry_run else 'deleted'}={would_delete if dry_run else deleted} "
        f"skipped={skipped} synced_suggestarr={synced} errors={errors}"
    )
    db.update_seer_request_prune_settings(
        last_run_at=_utcnow_for_db(),
        last_run_status=("dry_run" if dry_run else "ok"),
        last_run_summary=summary,
    )
    logger.info("Seer request prune finished: %s", summary)
    return {
        "status": "ok",
        "summary": summary,
        "dry_run": dry_run,
        "would_delete": would_delete,
        "deleted": deleted,
        "skipped": skipped,
        "synced_suggestarr": synced,
        "errors": errors,
    }
