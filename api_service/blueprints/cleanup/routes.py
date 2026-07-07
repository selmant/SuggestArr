"""Cleanup blueprint — settings + manual run + audit log for the cleanup automation."""

from flask import Blueprint, jsonify, request

from api_service.auth.limiter import limiter
from api_service.auth.middleware import require_role
from api_service.config.logger_manager import LoggerManager
from api_service.db.database_manager import DatabaseManager
from api_service.jobs.cleanup_automation import execute_cleanup_job, _run_lock as _shared_run_lock
from api_service.jobs.seer_import_automation import (
    execute_seer_import_job,
    _run_lock as _shared_import_run_lock,
)
from api_service.jobs.seer_request_prune_automation import (
    execute_seer_request_prune_job,
    _run_lock as _shared_prune_run_lock,
)
from api_service.utils.asyncio_loop import run_coroutine_sync

cleanup_bp = Blueprint("cleanup", __name__)
_run_lock = _shared_run_lock
_prune_run_lock = _shared_prune_run_lock
_import_run_lock = _shared_import_run_lock
logger = LoggerManager.get_logger("CleanupRoute")


@cleanup_bp.route("/settings", methods=["GET"])
def cleanup_settings_get():
    try:
        return jsonify({"status": "success", "settings": DatabaseManager().get_cleanup_settings()}), 200
    except Exception as exc:
        logger.error("Failed to fetch cleanup settings: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 500


@cleanup_bp.route("/settings", methods=["POST"])
@require_role("admin")
@limiter.limit("30 per minute")
def cleanup_settings_set():
    try:
        data = request.json or {}
        enabled = data.get("enabled")
        dry_run = data.get("dry_run")
        grace_days = data.get("grace_days")

        if grace_days is not None:
            try:
                grace_days = int(grace_days)
            except (TypeError, ValueError):
                return jsonify({"status": "error", "message": "grace_days must be an integer"}), 400
            if grace_days < 1 or grace_days > 365:
                return jsonify({"status": "error", "message": "grace_days must be between 1 and 365"}), 400

        for key, value in (("enabled", enabled), ("dry_run", dry_run)):
            if value is not None and not isinstance(value, bool):
                return jsonify({"status": "error", "message": f"{key} must be a boolean"}), 400

        settings = DatabaseManager().update_cleanup_settings(
            enabled=enabled, dry_run=dry_run, grace_days=grace_days
        )
        return jsonify({"status": "success", "settings": settings}), 200
    except Exception as exc:
        logger.error("Failed to update cleanup settings: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 500


@cleanup_bp.route("/run", methods=["POST"])
@require_role("admin")
def cleanup_run_now():
    if not _run_lock.acquire(blocking=False):
        return jsonify({
            "status": "error",
            "code": "already_running",
            "message": "A cleanup run is already in progress. Please wait for it to finish.",
        }), 409
    try:
        data = request.json or {}
        override_dry_run = data.get("dry_run")
        if override_dry_run is not None and not isinstance(override_dry_run, bool):
            return jsonify({"status": "error", "message": "dry_run must be a boolean"}), 400
        result = run_coroutine_sync(
            execute_cleanup_job(force_run=True, override_dry_run=override_dry_run),
            logger,
        )
        return jsonify({"status": "success", "result": result}), 200
    except Exception as exc:
        logger.error("Manual cleanup run failed: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 500
    finally:
        try:
            _run_lock.release()
        except RuntimeError:
            pass


@cleanup_bp.route("/log", methods=["GET"])
def cleanup_log_list():
    try:
        try:
            limit = int(request.args.get("limit", 100))
        except (TypeError, ValueError):
            limit = 100
        limit = max(1, min(500, limit))
        rows = DatabaseManager().get_cleanup_log(limit=limit)
        return jsonify({"status": "success", "log": rows}), 200
    except Exception as exc:
        logger.error("Failed to fetch cleanup log: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 500


def _validate_retention_days(value, field_name: str):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None, jsonify({"status": "error", "message": f"{field_name} must be an integer"}), 400
    if parsed < 1 or parsed > 365:
        return None, jsonify({"status": "error", "message": f"{field_name} must be between 1 and 365"}), 400
    return parsed, None, None


@cleanup_bp.route("/seer-prune/settings", methods=["GET"])
def seer_prune_settings_get():
    try:
        return jsonify({
            "status": "success",
            "settings": DatabaseManager().get_seer_request_prune_settings(),
        }), 200
    except Exception as exc:
        logger.error("Failed to fetch Seer request prune settings: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 500


@cleanup_bp.route("/seer-prune/settings", methods=["POST"])
@require_role("admin")
@limiter.limit("30 per minute")
def seer_prune_settings_set():
    try:
        data = request.json or {}
        updates = {}
        for key in ("enabled", "dry_run", "sync_suggestarr"):
            value = data.get(key)
            if value is not None:
                if not isinstance(value, bool):
                    return jsonify({"status": "error", "message": f"{key} must be a boolean"}), 400
                updates[key] = value

        for field in ("declined_days", "failed_days", "completed_days", "deleted_days"):
            value = data.get(field)
            if value is not None:
                parsed, error_response, status_code = _validate_retention_days(value, field)
                if error_response is not None:
                    return error_response, status_code
                updates[field] = parsed

        settings = DatabaseManager().update_seer_request_prune_settings(**updates)
        return jsonify({"status": "success", "settings": settings}), 200
    except Exception as exc:
        logger.error("Failed to update Seer request prune settings: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 500


@cleanup_bp.route("/seer-prune/run", methods=["POST"])
@require_role("admin")
def seer_prune_run_now():
    if not _prune_run_lock.acquire(blocking=False):
        return jsonify({
            "status": "error",
            "code": "already_running",
            "message": "A Seer request prune run is already in progress. Please wait for it to finish.",
        }), 409
    try:
        data = request.json or {}
        override_dry_run = data.get("dry_run")
        if override_dry_run is not None and not isinstance(override_dry_run, bool):
            return jsonify({"status": "error", "message": "dry_run must be a boolean"}), 400
        result = run_coroutine_sync(
            execute_seer_request_prune_job(force_run=True, override_dry_run=override_dry_run),
            logger,
        )
        return jsonify({"status": "success", "result": result}), 200
    except Exception as exc:
        logger.error("Manual Seer request prune run failed: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 500
    finally:
        try:
            _prune_run_lock.release()
        except RuntimeError:
            pass


@cleanup_bp.route("/seer-prune/log", methods=["GET"])
def seer_prune_log_list():
    try:
        try:
            limit = int(request.args.get("limit", 100))
        except (TypeError, ValueError):
            limit = 100
        limit = max(1, min(500, limit))
        rows = DatabaseManager().get_seer_request_prune_log(limit=limit)
        return jsonify({"status": "success", "log": rows}), 200
    except Exception as exc:
        logger.error("Failed to fetch Seer request prune log: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 500


@cleanup_bp.route("/seer-import/settings", methods=["GET"])
def seer_import_settings_get():
    try:
        return jsonify({
            "status": "success",
            "settings": DatabaseManager().get_seer_import_settings(),
        }), 200
    except Exception as exc:
        logger.error("Failed to fetch Seer import settings: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 500


@cleanup_bp.route("/seer-import/settings", methods=["POST"])
@require_role("admin")
@limiter.limit("30 per minute")
def seer_import_settings_set():
    try:
        data = request.json or {}
        updates = {}
        for key in ("enabled", "dry_run"):
            value = data.get(key)
            if value is not None:
                if not isinstance(value, bool):
                    return jsonify({"status": "error", "message": f"{key} must be a boolean"}), 400
                updates[key] = value
        status_filter = data.get("status_filter")
        if status_filter is not None:
            if status_filter not in ("all", "pending"):
                return jsonify({"status": "error", "message": "status_filter must be all or pending"}), 400
            updates["status_filter"] = status_filter

        settings = DatabaseManager().update_seer_import_settings(**updates)
        return jsonify({"status": "success", "settings": settings}), 200
    except Exception as exc:
        logger.error("Failed to update Seer import settings: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 500


@cleanup_bp.route("/seer-import/run", methods=["POST"])
@require_role("admin")
def seer_import_run_now():
    if not _import_run_lock.acquire(blocking=False):
        return jsonify({
            "status": "error",
            "code": "already_running",
            "message": "A Seer import run is already in progress. Please wait for it to finish.",
        }), 409
    try:
        data = request.json or {}
        override_dry_run = data.get("dry_run")
        if override_dry_run is not None and not isinstance(override_dry_run, bool):
            return jsonify({"status": "error", "message": "dry_run must be a boolean"}), 400
        result = run_coroutine_sync(
            execute_seer_import_job(force_run=True, override_dry_run=override_dry_run),
            logger,
        )
        return jsonify({"status": "success", "result": result}), 200
    except Exception as exc:
        logger.error("Manual Seer import run failed: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 500
    finally:
        try:
            _import_run_lock.release()
        except RuntimeError:
            pass


@cleanup_bp.route("/seer-import/log", methods=["GET"])
def seer_import_log_list():
    try:
        try:
            limit = int(request.args.get("limit", 100))
        except (TypeError, ValueError):
            limit = 100
        limit = max(1, min(500, limit))
        rows = DatabaseManager().get_seer_import_log(limit=limit)
        return jsonify({"status": "success", "log": rows}), 200
    except Exception as exc:
        logger.error("Failed to fetch Seer import log: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 500
