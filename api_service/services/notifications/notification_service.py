"""High-level notification dispatch for SuggestArr automation events."""

from __future__ import annotations

from typing import Any

from api_service.config.logger_manager import LoggerManager
from api_service.db.database_manager import DatabaseManager
from api_service.services.config_service import ConfigService
from api_service.services.notifications.ntfy_client import NtfyClient, NtfyPublishError

logger = LoggerManager.get_logger(__name__)

_ERROR_MESSAGE_MAX_LEN = 200


def _truncate_error(message: str | None) -> str:
    """Return a short error string suitable for mobile notifications."""
    if not message:
        return 'Unknown error'
    text = message.strip()
    if len(text) <= _ERROR_MESSAGE_MAX_LEN:
        return text
    return text[: _ERROR_MESSAGE_MAX_LEN - 3] + '...'


def _as_bool(value: Any, default: bool = False) -> bool:
    """Coerce config values that may be bool or string."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', '1', 'yes', 'on')
    return bool(value)


class NotificationService:
    """Decide whether to notify, format payloads, and publish via ntfy."""

    def __init__(self, db: DatabaseManager | None = None) -> None:
        """Initialize the service.

        :param db: Optional database manager (defaults to singleton).
        """
        self.db = db or DatabaseManager()

    def _load_config(self, config_override: dict | None = None) -> dict:
        """Return merged runtime config, optionally overridden for test sends."""
        config = dict(ConfigService.get_runtime_config())
        if config_override:
            config.update(config_override)
        return config

    def _is_enabled(self, config: dict) -> bool:
        """Return True when ntfy notifications are globally enabled."""
        return _as_bool(config.get('NTFY_ENABLED'), default=False)

    def _should_notify(self, config: dict, event_key: str) -> bool:
        """Return True when the given event toggle is enabled."""
        toggle_map = {
            'completed': 'NTFY_NOTIFY_ON_SUCCESS',
            'failed': 'NTFY_NOTIFY_ON_FAILURE',
            'skipped': 'NTFY_NOTIFY_ON_SKIPPED',
            'queue_failure': 'NTFY_NOTIFY_ON_QUEUE_FAILURE',
        }
        toggle = toggle_map.get(event_key)
        if not toggle:
            return False
        default = event_key != 'completed'
        return _as_bool(config.get(toggle), default=default)

    def _build_client(self, config: dict) -> NtfyClient | None:
        """Construct an ntfy client when server URL and topic are configured."""
        server_url = (config.get('NTFY_SERVER_URL') or '').strip()
        topic = (config.get('NTFY_TOPIC') or '').strip()
        if not server_url or not topic:
            return None

        access_token = (config.get('NTFY_ACCESS_TOKEN') or '').strip() or None
        username = (config.get('NTFY_USERNAME') or '').strip() or None
        password = (config.get('NTFY_PASSWORD') or '').strip() or None

        return NtfyClient(
            server_url,
            topic,
            access_token=access_token,
            username=username,
            password=password,
        )

    def _publish_safe(
        self,
        config: dict,
        *,
        message: str,
        title: str,
        priority: int,
        tags: list[str],
    ) -> None:
        """Publish a notification, logging and swallowing delivery errors."""
        if not self._is_enabled(config):
            return

        client = self._build_client(config)
        if client is None:
            logger.debug('ntfy publish skipped: server URL or topic not configured')
            return

        try:
            client.publish(message, title=title, priority=priority, tags=tags)
        except NtfyPublishError as exc:
            logger.warning('ntfy delivery failed (non-fatal): %s', exc)
        except Exception as exc:
            logger.warning('ntfy delivery failed unexpectedly (non-fatal): %s', exc)

    def _lookup_execution(self, exec_id: int) -> dict[str, Any] | None:
        """Load job metadata for an execution history record."""
        query = """
            SELECT j.name, j.job_type
            FROM job_execution_history h
            JOIN discover_jobs j ON h.job_id = j.id
            WHERE h.id = ?
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            sql = query.replace('?', '%s') if self.db.db_type in ('mysql', 'postgres') else query
            cursor.execute(sql, (exec_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return {'job_name': row[0], 'job_type': row[1]}

    def notify_execution_end(
        self,
        exec_id: int,
        status: str,
        results_count: int = 0,
        requested_count: int = 0,
        error_message: str | None = None,
    ) -> None:
        """Send a notification for a job execution outcome when enabled.

        :param exec_id: Execution history record ID.
        :param status: Final status (``completed``, ``failed``, or ``skipped``).
        :param results_count: Number of results found.
        :param requested_count: Number of items requested to Seer.
        :param error_message: Error text when failed.
        """
        config = self._load_config()
        if not self._is_enabled(config) or not self._should_notify(config, status):
            return

        job_info = self._lookup_execution(exec_id) or {}
        job_name = job_info.get('job_name') or f'Job #{exec_id}'
        job_type = job_info.get('job_type') or 'unknown'

        if status == 'completed':
            message = (
                f'{job_name} ({job_type})\n'
                f'Results found: {results_count}\n'
                f'Requested: {requested_count}'
            )
            self._publish_safe(
                config,
                message=message,
                title='SuggestArr: Job completed',
                priority=3,
                tags=['white_check_mark', 'suggestarr'],
            )
        elif status == 'failed':
            message = (
                f'{job_name} ({job_type})\n'
                f'Error: {_truncate_error(error_message)}'
            )
            self._publish_safe(
                config,
                message=message,
                title='SuggestArr: Job failed',
                priority=4,
                tags=['warning', 'suggestarr'],
            )
        elif status == 'skipped':
            reason = error_message or 'Job was skipped.'
            message = f'{job_name}\n{reason}'
            self._publish_safe(
                config,
                message=message,
                title='SuggestArr: Job skipped',
                priority=3,
                tags=['pause_button', 'suggestarr'],
            )

    def notify_queue_permanent_failure(
        self,
        media_type: str,
        tmdb_id: int | str,
        retry_count: int,
    ) -> None:
        """Send a notification when a queued request permanently fails.

        :param media_type: Media type (``movie`` or ``tv``).
        :param tmdb_id: TMDb identifier.
        :param retry_count: Final retry count when marked failed.
        """
        config = self._load_config()
        if not self._is_enabled(config) or not self._should_notify(config, 'queue_failure'):
            return

        message = (
            f'Media type: {media_type}\n'
            f'TMDb ID: {tmdb_id}\n'
            f'Retries: {retry_count}'
        )
        self._publish_safe(
            config,
            message=message,
            title='SuggestArr: Request failed',
            priority=4,
            tags=['x', 'suggestarr'],
        )

    def send_test_notification(self, config_override: dict | None = None) -> dict:
        """Publish a test notification and return success/failure details.

        :param config_override: Optional flat config values from the test endpoint.
        :return: Dict with ``status`` (``success`` or ``error``) and ``message``.
        """
        config = self._load_config(config_override)
        server_url = (config.get('NTFY_SERVER_URL') or '').strip()
        topic = (config.get('NTFY_TOPIC') or '').strip()

        if not server_url:
            return {'status': 'error', 'message': 'NTFY_SERVER_URL is required.'}
        if not topic:
            return {'status': 'error', 'message': 'NTFY_TOPIC is required.'}

        client = self._build_client(config)
        if client is None:
            return {'status': 'error', 'message': 'Unable to build ntfy client.'}

        try:
            client.publish(
                'If you see this, ntfy is configured correctly.',
                title='SuggestArr: Test notification',
                priority=3,
                tags=['suggestarr'],
            )
        except NtfyPublishError as exc:
            return {'status': 'error', 'message': str(exc)}

        return {'status': 'success', 'message': 'Test notification sent successfully.'}
