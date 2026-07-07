"""Tests for queue worker ntfy notification hooks."""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from api_service.jobs import queue_worker


class TestQueueWorkerNotifications(unittest.IsolatedAsyncioTestCase):
    async def test_permanent_failure_notifies_once(self):
        db = MagicMock()
        db.reset_stale_inflight.return_value = 0
        db.get_due_requests.return_value = [{
            'id': 1,
            'tmdb_id': 550,
            'media_type': 'movie',
            'retry_count': 4,
            'payload': json.dumps({'profileId': 1, 'rootFolder': '/movies'}),
        }]
        db.check_request_exists.return_value = False

        seer = AsyncMock()
        seer.submit_queued_request = AsyncMock(return_value=False)
        seer.__aenter__ = AsyncMock(return_value=seer)
        seer.__aexit__ = AsyncMock(return_value=False)

        with patch('api_service.jobs.queue_worker.DatabaseManager', return_value=db), \
             patch('api_service.jobs.queue_worker.ConfigService.get_runtime_config', return_value={
                 'SEER_API_URL': 'http://seer',
                 'SEER_TOKEN': 'token',
             }), \
             patch('api_service.jobs.queue_worker.SeerClient', return_value=seer), \
             patch('api_service.jobs.queue_worker.NotificationService') as mock_notify_cls:
            await queue_worker._run_worker()

        db.mark_pending_failed.assert_called_once_with(1, 5)
        mock_notify_cls.return_value.notify_queue_permanent_failure.assert_called_once_with(
            'movie', 550, 5,
        )
        db.increment_pending_retry.assert_not_called()

    async def test_retry_does_not_notify(self):
        db = MagicMock()
        db.reset_stale_inflight.return_value = 0
        db.get_due_requests.return_value = [{
            'id': 2,
            'tmdb_id': 1399,
            'media_type': 'tv',
            'retry_count': 1,
            'payload': json.dumps({'profileId': 1, 'rootFolder': '/tv'}),
        }]
        db.check_request_exists.return_value = False

        seer = AsyncMock()
        seer.submit_queued_request = AsyncMock(return_value=False)
        seer.__aenter__ = AsyncMock(return_value=seer)
        seer.__aexit__ = AsyncMock(return_value=False)

        with patch('api_service.jobs.queue_worker.DatabaseManager', return_value=db), \
             patch('api_service.jobs.queue_worker.ConfigService.get_runtime_config', return_value={
                 'SEER_API_URL': 'http://seer',
                 'SEER_TOKEN': 'token',
             }), \
             patch('api_service.jobs.queue_worker.SeerClient', return_value=seer), \
             patch('api_service.jobs.queue_worker.NotificationService') as mock_notify_cls:
            await queue_worker._run_worker()

        db.increment_pending_retry.assert_called_once()
        db.mark_pending_failed.assert_not_called()
        mock_notify_cls.return_value.notify_queue_permanent_failure.assert_not_called()

    async def test_corrupt_payload_notifies_permanent_failure(self):
        db = MagicMock()
        db.reset_stale_inflight.return_value = 0
        db.get_due_requests.return_value = [{
            'id': 3,
            'tmdb_id': 99,
            'media_type': 'movie',
            'retry_count': 0,
            'payload': '{not-json',
        }]

        seer = AsyncMock()
        seer.__aenter__ = AsyncMock(return_value=seer)
        seer.__aexit__ = AsyncMock(return_value=False)

        with patch('api_service.jobs.queue_worker.DatabaseManager', return_value=db), \
             patch('api_service.jobs.queue_worker.ConfigService.get_runtime_config', return_value={
                 'SEER_API_URL': 'http://seer',
                 'SEER_TOKEN': 'token',
             }), \
             patch('api_service.jobs.queue_worker.SeerClient', return_value=seer), \
             patch('api_service.jobs.queue_worker.NotificationService') as mock_notify_cls:
            await queue_worker._run_worker()

        db.mark_pending_failed.assert_called_once_with(3, 0)
        mock_notify_cls.return_value.notify_queue_permanent_failure.assert_called_once_with(
            'movie', 99, 0,
        )


if __name__ == '__main__':
    unittest.main()
