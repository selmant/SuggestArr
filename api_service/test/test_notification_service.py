"""Tests for NotificationService event formatting and gating."""

import unittest
from unittest.mock import MagicMock, patch

from api_service.services.notifications.notification_service import NotificationService


def _enabled_config(**overrides):
    config = {
        'NTFY_ENABLED': True,
        'NTFY_SERVER_URL': 'https://ntfy.sh',
        'NTFY_TOPIC': 'alerts',
        'NTFY_NOTIFY_ON_SUCCESS': True,
        'NTFY_NOTIFY_ON_FAILURE': True,
        'NTFY_NOTIFY_ON_SKIPPED': True,
        'NTFY_NOTIFY_ON_QUEUE_FAILURE': True,
    }
    config.update(overrides)
    return config


class TestNotificationService(unittest.TestCase):
    @patch('api_service.services.notifications.notification_service.NtfyClient')
    @patch.object(NotificationService, '_load_config')
    def test_disabled_config_skips_publish(self, mock_load, mock_client_cls):
        mock_load.return_value = {'NTFY_ENABLED': False}
        service = NotificationService(db=MagicMock())
        service.notify_queue_permanent_failure('movie', 550, 5)
        mock_client_cls.assert_not_called()

    @patch('api_service.services.notifications.notification_service.NtfyClient')
    @patch.object(NotificationService, '_load_config')
    def test_missing_topic_skips_publish(self, mock_load, mock_client_cls):
        mock_load.return_value = {
            'NTFY_ENABLED': True,
            'NTFY_SERVER_URL': 'https://ntfy.sh',
            'NTFY_TOPIC': '',
        }
        service = NotificationService(db=MagicMock())
        service.notify_queue_permanent_failure('movie', 550, 5)
        mock_client_cls.assert_not_called()

    @patch('api_service.services.notifications.notification_service.NtfyClient')
    @patch.object(NotificationService, '_load_config')
    def test_success_toggle_off_suppresses_completed(self, mock_load, mock_client_cls):
        mock_load.return_value = _enabled_config(NTFY_NOTIFY_ON_SUCCESS=False)
        service = NotificationService(db=MagicMock())
        service.notify_execution_end(1, 'completed', results_count=3, requested_count=2)
        mock_client_cls.assert_not_called()

    @patch('api_service.services.notifications.notification_service.NtfyClient')
    @patch.object(NotificationService, '_lookup_execution')
    @patch.object(NotificationService, '_load_config')
    def test_completed_notification_format(self, mock_load, mock_lookup, mock_client_cls):
        mock_load.return_value = _enabled_config()
        mock_lookup.return_value = {'job_name': 'Daily Discover', 'job_type': 'discover'}
        client = MagicMock()
        mock_client_cls.return_value = client

        service = NotificationService(db=MagicMock())
        service.notify_execution_end(10, 'completed', results_count=5, requested_count=2)

        client.publish.assert_called_once_with(
            'Daily Discover (discover)\nResults found: 5\nRequested: 2',
            title='SuggestArr: Job completed',
            priority=3,
            tags=['white_check_mark', 'suggestarr'],
        )

    @patch('api_service.services.notifications.notification_service.NtfyClient')
    @patch.object(NotificationService, '_lookup_execution')
    @patch.object(NotificationService, '_load_config')
    def test_failed_notification_format(self, mock_load, mock_lookup, mock_client_cls):
        mock_load.return_value = _enabled_config()
        mock_lookup.return_value = {'job_name': 'Recs', 'job_type': 'recommendation'}
        client = MagicMock()
        mock_client_cls.return_value = client

        service = NotificationService(db=MagicMock())
        service.notify_execution_end(11, 'failed', error_message='Seer timeout')

        client.publish.assert_called_once()
        kwargs = client.publish.call_args.kwargs
        self.assertEqual(kwargs['title'], 'SuggestArr: Job failed')
        self.assertEqual(kwargs['priority'], 4)
        self.assertEqual(kwargs['tags'], ['warning', 'suggestarr'])
        self.assertIn('Seer timeout', client.publish.call_args.args[0])

    @patch('api_service.services.notifications.notification_service.NtfyClient')
    @patch.object(NotificationService, '_lookup_execution')
    @patch.object(NotificationService, '_load_config')
    def test_skipped_notification_format(self, mock_load, mock_lookup, mock_client_cls):
        mock_load.return_value = _enabled_config()
        mock_lookup.return_value = {'job_name': 'Nightly', 'job_type': 'discover'}
        client = MagicMock()
        mock_client_cls.return_value = client

        service = NotificationService(db=MagicMock())
        service.notify_execution_end(
            12,
            'skipped',
            error_message='Paused: Seer has pending requests awaiting approval or denial.',
        )

        client.publish.assert_called_once()
        kwargs = client.publish.call_args.kwargs
        self.assertEqual(kwargs['title'], 'SuggestArr: Job skipped')
        self.assertEqual(kwargs['tags'], ['pause_button', 'suggestarr'])

    @patch('api_service.services.notifications.notification_service.NtfyClient')
    @patch.object(NotificationService, '_load_config')
    def test_queue_failure_notification_format(self, mock_load, mock_client_cls):
        mock_load.return_value = _enabled_config()
        client = MagicMock()
        mock_client_cls.return_value = client

        service = NotificationService(db=MagicMock())
        service.notify_queue_permanent_failure('tv', 1399, 5)

        client.publish.assert_called_once_with(
            'Media type: tv\nTMDb ID: 1399\nRetries: 5',
            title='SuggestArr: Request failed',
            priority=4,
            tags=['x', 'suggestarr'],
        )

    @patch('api_service.services.notifications.notification_service.NtfyClient')
    @patch.object(NotificationService, '_load_config')
    def test_delivery_error_is_swallowed(self, mock_load, mock_client_cls):
        from api_service.services.notifications.ntfy_client import NtfyPublishError

        mock_load.return_value = _enabled_config()
        client = MagicMock()
        client.publish.side_effect = NtfyPublishError('403 forbidden')
        mock_client_cls.return_value = client

        service = NotificationService(db=MagicMock())
        service.notify_queue_permanent_failure('movie', 1, 5)

    @patch('api_service.services.notifications.notification_service.NtfyClient')
    @patch.object(NotificationService, '_load_config')
    def test_send_test_notification_success(self, mock_load, mock_client_cls):
        mock_load.return_value = _enabled_config()
        client = MagicMock()
        mock_client_cls.return_value = client

        service = NotificationService(db=MagicMock())
        result = service.send_test_notification()

        self.assertEqual(result['status'], 'success')
        client.publish.assert_called_once()

    @patch.object(NotificationService, '_load_config')
    def test_send_test_notification_validation_error(self, mock_load):
        mock_load.return_value = {'NTFY_SERVER_URL': '', 'NTFY_TOPIC': ''}
        service = NotificationService(db=MagicMock())
        result = service.send_test_notification()
        self.assertEqual(result['status'], 'error')
        self.assertIn('NTFY_SERVER_URL', result['message'])


if __name__ == '__main__':
    unittest.main()
