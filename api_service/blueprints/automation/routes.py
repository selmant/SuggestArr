import asyncio
import threading
from asgiref.sync import async_to_sync
from flask import Blueprint, jsonify, request
from api_service.auth.limiter import limiter
from api_service.auth.middleware import require_role
from api_service.automate_process import ContentAutomation
from api_service.config.logger_manager import LoggerManager
from api_service.db.database_manager import DatabaseManager
from api_service.services.trakt.request_actions import (
    get_request_trakt_status,
    get_request_trakt_statuses_batch,
    mark_request_watched,
    set_request_rating,
    unmark_request_watched,
)
from api_service.services.seer.request_actions import (
    approve_request as approve_seer_request,
    decline_request as decline_seer_request,
    get_request_details,
    get_request_seer_status,
    get_request_seer_statuses_batch,
    request_collection_part,
)
from api_service.utils.asyncio_loop import close_event_loop

logger = LoggerManager().get_logger("AutomationRoute")
automation_bp = Blueprint('automation', __name__)

_force_run_lock = threading.Lock()
_force_run_running = False
_VALID_MEDIA_TYPES = frozenset({"movie", "tv"})


def _get_json() -> dict:
    return request.get_json(silent=True) or {}


def _validate_media_type(media_type: str) -> str:
    normalized = str(media_type or "").lower()
    if normalized not in _VALID_MEDIA_TYPES:
        raise ValueError("media_type must be movie or tv")
    return normalized


def _run_automation_in_background():
    """Run the automation in a dedicated thread with its own event loop."""
    global _force_run_running
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        content_automation = loop.run_until_complete(ContentAutomation.create())
        loop.run_until_complete(content_automation.run())
        logger.info("Force run completed successfully.")
    except Exception as e:
        logger.error(f'Background force run error: {str(e)}', exc_info=True)
    finally:
        close_event_loop(loop, logger)
        with _force_run_lock:
            _force_run_running = False


@automation_bp.route('/force_run', methods=['POST'])
@require_role('admin')
@limiter.limit("5 per minute")
def run_now():
    """
    Endpoint to execute the automation process in a background thread.
    Returns immediately while the task runs asynchronously.
    """
    global _force_run_running
    with _force_run_lock:
        if _force_run_running:
            return jsonify({'status': 'busy', 'message': 'A force run is already in progress.'}), 409
        _force_run_running = True

    thread = threading.Thread(target=_run_automation_in_background, daemon=True)
    thread.start()
    return jsonify({'status': 'success', 'message': 'Task started in the background!'}), 202

@automation_bp.route('/requests', methods=['GET'])
def get_requests():
    """Get all automation requests grouped by source with pagination and sorting."""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 8, type=int)
        sort_by = request.args.get('sort_by', 'date-desc', type=str)
        seer_status_filter = request.args.get('seer_status', 'all', type=str)
        
        # Validte sort_by
        valid_sorts = ['date-desc', 'date-asc', 'title-asc', 'title-desc', 'rating-desc', 'rating-asc']
        if sort_by not in valid_sorts:
            sort_by = 'date-desc'
        
        db_manager = DatabaseManager()
        result = db_manager.get_all_requests_grouped_by_source(
            page=page, 
            per_page=per_page,
            sort_by=sort_by,
            seer_status_filter=seer_status_filter,
        )
        
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error retrieving requests: {e}", exc_info=True)
        return jsonify({"error": "An internal error occurred"}), 500


@automation_bp.route('/requests/flat', methods=['GET'])
def get_requests_flat():
    """Get automation requests as a flat paginated list."""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 24, type=int)
        sort_by = request.args.get('sort_by', 'date-desc', type=str)
        seer_status_filter = request.args.get('seer_status', 'all', type=str)

        valid_sorts = ['date-desc', 'date-asc', 'title-asc', 'title-desc', 'rating-desc', 'rating-asc']
        if sort_by not in valid_sorts:
            sort_by = 'date-desc'

        per_page = max(1, min(per_page, 100))
        db_manager = DatabaseManager()
        result = db_manager.get_all_requests_flat(
            page=page,
            per_page=per_page,
            sort_by=sort_by,
            seer_status_filter=seer_status_filter,
        )
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error retrieving flat requests: {e}", exc_info=True)
        return jsonify({"error": "An internal error occurred"}), 500


@automation_bp.route('/requests/count', methods=['GET'])
def get_requests_count():
    """Return a deterministic count for the Requests-page filters."""
    try:
        search = request.args.get('search', '', type=str)
        media_type = request.args.get('media_type', 'all', type=str)
        seer_status_filter = request.args.get('seer_status', 'all', type=str)
        if media_type not in ('all', 'movie', 'tv'):
            media_type = 'all'
        count = DatabaseManager().count_requests(
            search=search,
            media_type=media_type,
            seer_status_filter=seer_status_filter,
        )
        return jsonify({'count': count}), 200
    except Exception as e:
        logger.error(f"Error counting requests: {e}", exc_info=True)
        return jsonify({"error": "An internal error occurred"}), 500


@automation_bp.route('/requests/source/<source_id>', methods=['GET'])
def get_requests_by_source(source_id: str):
    """Get paginated requests for one watched-content source group."""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        sort_by = request.args.get('sort_by', 'date-desc', type=str)
        seer_status_filter = request.args.get('seer_status', 'all', type=str)

        valid_sorts = ['date-desc', 'date-asc', 'title-asc', 'title-desc', 'rating-desc', 'rating-asc']
        if sort_by not in valid_sorts:
            sort_by = 'date-desc'

        per_page = max(1, min(per_page, 200))
        db_manager = DatabaseManager()
        result = db_manager.get_requests_for_source(
            source_id=source_id,
            page=page,
            per_page=per_page,
            sort_by=sort_by,
            seer_status_filter=seer_status_filter,
        )
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error retrieving source requests: {e}", exc_info=True)
        return jsonify({"error": "An internal error occurred"}), 500


@automation_bp.route('/requests/ai-search', methods=['GET'])
def get_ai_requests():
    """Get requests originated from AI Search with pagination and sorting."""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 12, type=int)
        sort_by = request.args.get('sort_by', 'date-desc', type=str)

        valid_sorts = ['date-desc', 'date-asc', 'title-asc', 'title-desc']
        if sort_by not in valid_sorts:
            sort_by = 'date-desc'

        db_manager = DatabaseManager()
        result = db_manager.get_ai_search_requests(page=page, per_page=per_page, sort_by=sort_by)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error retrieving AI search requests: {e}", exc_info=True)
        return jsonify({"error": "An internal error occurred"}), 500


@automation_bp.route('/requests/archived', methods=['GET'])
def get_archived_requests():
    """Get archived automation requests as a flat paginated list."""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 24, type=int)
        sort_by = request.args.get('sort_by', 'date-desc', type=str)

        valid_sorts = ['date-desc', 'date-asc']
        if sort_by not in valid_sorts:
            sort_by = 'date-desc'

        per_page = max(1, min(per_page, 100))
        db_manager = DatabaseManager()
        result = db_manager.get_archived_requests_flat(
            page=page,
            per_page=per_page,
            sort_by=sort_by,
        )
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error retrieving archived requests: {e}", exc_info=True)
        return jsonify({"error": "An internal error occurred"}), 500


@automation_bp.route('/requests/stats', methods=['GET'])
def get_requests_stats():
    """Get statistics for automation requests."""
    try:
        db_manager = DatabaseManager()
        stats = db_manager.get_requests_stats()
        return jsonify(stats), 200
    except Exception as e:
        logger.error(f"Error retrieving request stats: {e}", exc_info=True)
        return jsonify({"error": "An internal error occurred"}), 500


@automation_bp.route('/requests/<tmdb_id>/<media_type>/trakt/status', methods=['GET'])
def get_request_trakt_status_route(tmdb_id: str, media_type: str):
    """Return Trakt watched/rating status for a request's media user."""
    try:
        media_type = _validate_media_type(media_type)
        user_id = request.args.get('user_id', type=str)
        if not user_id:
            return jsonify({"message": "user_id is required"}), 400
        result = async_to_sync(get_request_trakt_status)(
            DatabaseManager(), tmdb_id, media_type, user_id,
        )
        return jsonify(result), 200
    except ValueError as exc:
        message = str(exc)
        status = 404 if "not found" in message.lower() or "not linked" in message.lower() else 400
        return jsonify({"message": message}), status
    except RuntimeError as exc:
        logger.warning("Trakt status failed for %s/%s: %s", media_type, tmdb_id, exc)
        return jsonify({"message": str(exc)}), 502
    except Exception as exc:
        logger.error("Error fetching Trakt status: %s", exc, exc_info=True)
        return jsonify({"error": "An internal error occurred"}), 500


@automation_bp.route('/requests/trakt/status-batch', methods=['POST'])
def get_request_trakt_statuses_batch_route():
    """Return Trakt watched/rating status for many requests in one cached sync pass."""
    try:
        payload = _get_json()
        user_id = str(payload.get("user_id") or "")
        if not user_id:
            return jsonify({"message": "user_id is required"}), 400
        items = payload.get("items")
        if not isinstance(items, list):
            return jsonify({"message": "items must be a list"}), 400
        result = async_to_sync(get_request_trakt_statuses_batch)(
            DatabaseManager(),
            user_id,
            items,
        )
        return jsonify(result), 200
    except ValueError as exc:
        message = str(exc)
        status = 404 if "not found" in message.lower() or "not linked" in message.lower() else 400
        return jsonify({"message": message}), status
    except RuntimeError as exc:
        logger.warning("Trakt batch status failed: %s", exc)
        return jsonify({"message": str(exc)}), 502
    except Exception as exc:
        logger.error("Error fetching Trakt batch status: %s", exc, exc_info=True)
        return jsonify({"error": "An internal error occurred"}), 500


@automation_bp.route('/requests/<tmdb_id>/<media_type>/trakt/mark-watched', methods=['POST'])
def mark_request_watched_route(tmdb_id: str, media_type: str):
    """Mark a request as watched on Trakt for the request's media user."""
    try:
        media_type = _validate_media_type(media_type)
        payload = _get_json()
        user_id = str(payload.get("user_id") or "")
        if not user_id:
            return jsonify({"message": "user_id is required"}), 400
        result = async_to_sync(mark_request_watched)(
            DatabaseManager(),
            tmdb_id,
            media_type,
            user_id,
            str(payload.get("watched_at") or "now"),
            payload.get("rating_stars"),
        )
        return jsonify(result), 200
    except ValueError as exc:
        message = str(exc)
        status = 404 if "not found" in message.lower() or "not linked" in message.lower() else 400
        return jsonify({"message": message}), status
    except RuntimeError as exc:
        logger.warning("Trakt mark-watched failed for %s/%s: %s", media_type, tmdb_id, exc)
        return jsonify({"message": str(exc)}), 502
    except Exception as exc:
        logger.error("Error marking request watched on Trakt: %s", exc, exc_info=True)
        return jsonify({"error": "An internal error occurred"}), 500


@automation_bp.route('/requests/<tmdb_id>/<media_type>/trakt/unmark-watched', methods=['POST'])
def unmark_request_watched_route(tmdb_id: str, media_type: str):
    """Remove a request from Trakt watch history for the request's media user."""
    try:
        media_type = _validate_media_type(media_type)
        payload = _get_json()
        user_id = str(payload.get("user_id") or "")
        if not user_id:
            return jsonify({"message": "user_id is required"}), 400
        result = async_to_sync(unmark_request_watched)(
            DatabaseManager(),
            tmdb_id,
            media_type,
            user_id,
            bool(payload.get("remove_rating", False)),
        )
        return jsonify(result), 200
    except ValueError as exc:
        message = str(exc)
        status = 404 if "not found" in message.lower() or "not linked" in message.lower() else 400
        return jsonify({"message": message}), status
    except RuntimeError as exc:
        logger.warning("Trakt unmark failed for %s/%s: %s", media_type, tmdb_id, exc)
        return jsonify({"message": str(exc)}), 502
    except Exception as exc:
        logger.error("Error unmarking request on Trakt: %s", exc, exc_info=True)
        return jsonify({"error": "An internal error occurred"}), 500


@automation_bp.route('/requests/<tmdb_id>/<media_type>/trakt/rate', methods=['POST'])
def rate_request_route(tmdb_id: str, media_type: str):
    """Set a Trakt star rating for a request's media user."""
    try:
        media_type = _validate_media_type(media_type)
        payload = _get_json()
        user_id = str(payload.get("user_id") or "")
        if not user_id:
            return jsonify({"message": "user_id is required"}), 400
        if payload.get("rating_stars") is None:
            return jsonify({"message": "rating_stars is required"}), 400
        result = async_to_sync(set_request_rating)(
            DatabaseManager(), tmdb_id, media_type, user_id, payload.get("rating_stars"),
        )
        return jsonify(result), 200
    except ValueError as exc:
        message = str(exc)
        status = 404 if "not found" in message.lower() or "not linked" in message.lower() else 400
        return jsonify({"message": message}), status
    except RuntimeError as exc:
        logger.warning("Trakt rating failed for %s/%s: %s", media_type, tmdb_id, exc)
        return jsonify({"message": str(exc)}), 502
    except Exception as exc:
        logger.error("Error rating request on Trakt: %s", exc, exc_info=True)
        return jsonify({"error": "An internal error occurred"}), 500


@automation_bp.route('/requests/<tmdb_id>/<media_type>/details', methods=['GET'])
def get_request_details_route(tmdb_id: str, media_type: str):
    """Return rich Seer-backed metadata for a request item."""
    try:
        media_type = _validate_media_type(media_type)
        result = async_to_sync(get_request_details)(
            DatabaseManager(), tmdb_id, media_type,
        )
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    except RuntimeError as exc:
        logger.warning("Seer details failed for %s/%s: %s", media_type, tmdb_id, exc)
        return jsonify({"message": str(exc)}), 502
    except Exception as exc:
        logger.error("Error fetching request details: %s", exc, exc_info=True)
        return jsonify({"error": "An internal error occurred"}), 500


@automation_bp.route('/requests/collection/request', methods=['POST'])
@require_role('admin')
@limiter.limit("30 per minute")
def request_collection_part_route():
    """Enqueue a Seer request for a collection sibling, mirroring another request."""
    try:
        payload = _get_json()
        tmdb_id = payload.get("tmdb_id")
        media_type = payload.get("media_type", "movie")
        mirror_tmdb_id = payload.get("mirror_tmdb_id")
        mirror_media_type = payload.get("mirror_media_type", "movie")
        if tmdb_id is None or mirror_tmdb_id is None:
            return jsonify({"message": "tmdb_id and mirror_tmdb_id are required"}), 400
        media_type = _validate_media_type(media_type)
        mirror_media_type = _validate_media_type(mirror_media_type)
        result = async_to_sync(request_collection_part)(
            DatabaseManager(),
            tmdb_id=str(tmdb_id),
            media_type=media_type,
            mirror_tmdb_id=str(mirror_tmdb_id),
            mirror_media_type=mirror_media_type,
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
            collection_name=payload.get("collection_name"),
        )
        status = 202 if result.get("enqueued") else 200
        return jsonify(result), status
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    except RuntimeError as exc:
        logger.warning("Collection request failed: %s", exc)
        return jsonify({"message": str(exc)}), 502
    except Exception as exc:
        logger.error("Error requesting collection part: %s", exc, exc_info=True)
        return jsonify({"error": "An internal error occurred"}), 500


@automation_bp.route('/requests/<tmdb_id>/<media_type>/seer/status', methods=['GET'])
def get_request_seer_status_route(tmdb_id: str, media_type: str):
    """Return Seer approval status for a request item."""
    try:
        media_type = _validate_media_type(media_type)
        result = async_to_sync(get_request_seer_status)(
            DatabaseManager(), tmdb_id, media_type,
        )
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    except RuntimeError as exc:
        logger.warning("Seer status failed for %s/%s: %s", media_type, tmdb_id, exc)
        return jsonify({"message": str(exc)}), 502
    except Exception as exc:
        logger.error("Error fetching Seer status: %s", exc, exc_info=True)
        return jsonify({"error": "An internal error occurred"}), 500


@automation_bp.route('/requests/seer/status-batch', methods=['POST'])
def get_request_seer_statuses_batch_route():
    """Return Seer approval status for many request items in one pass."""
    try:
        payload = _get_json()
        items = payload.get("items")
        if not isinstance(items, list):
            return jsonify({"message": "items must be a list"}), 400
        result = async_to_sync(get_request_seer_statuses_batch)(
            DatabaseManager(),
            items,
        )
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    except RuntimeError as exc:
        logger.warning("Seer batch status failed: %s", exc)
        return jsonify({"message": str(exc)}), 502
    except Exception as exc:
        logger.error("Error fetching Seer batch status: %s", exc, exc_info=True)
        return jsonify({"error": "An internal error occurred"}), 500


@automation_bp.route('/requests/<tmdb_id>/<media_type>/seer/approve', methods=['POST'])
@require_role('admin')
def approve_seer_request_route(tmdb_id: str, media_type: str):
    """Approve pending Seer request(s) for a SuggestArr request item."""
    try:
        media_type = _validate_media_type(media_type)
        result = async_to_sync(approve_seer_request)(
            DatabaseManager(), tmdb_id, media_type,
        )
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    except RuntimeError as exc:
        logger.warning("Seer approve failed for %s/%s: %s", media_type, tmdb_id, exc)
        return jsonify({"message": str(exc)}), 502
    except Exception as exc:
        logger.error("Error approving Seer request: %s", exc, exc_info=True)
        return jsonify({"error": "An internal error occurred"}), 500


@automation_bp.route('/requests/<tmdb_id>/<media_type>/seer/decline', methods=['POST'])
@require_role('admin')
def decline_seer_request_route(tmdb_id: str, media_type: str):
    """Decline pending Seer request(s) for a SuggestArr request item."""
    try:
        media_type = _validate_media_type(media_type)
        result = async_to_sync(decline_seer_request)(
            DatabaseManager(), tmdb_id, media_type,
        )
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    except RuntimeError as exc:
        logger.warning("Seer decline failed for %s/%s: %s", media_type, tmdb_id, exc)
        return jsonify({"message": str(exc)}), 502
    except Exception as exc:
        logger.error("Error declining Seer request: %s", exc, exc_info=True)
        return jsonify({"error": "An internal error occurred"}), 500
