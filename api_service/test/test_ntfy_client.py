"""Tests for the ntfy HTTP publish client."""

import unittest
from unittest.mock import MagicMock, patch

import requests

from api_service.services.notifications.ntfy_client import NtfyClient, NtfyPublishError


class TestNtfyClient(unittest.TestCase):
    def test_publish_url_construction(self):
        client = NtfyClient('https://ntfy.sh/', 'mytopic')
        self.assertEqual(client.publish_url, 'https://ntfy.sh/mytopic')

    @patch('api_service.services.notifications.ntfy_client.requests.post')
    def test_publish_sends_headers_and_body(self, mock_post):
        response = MagicMock()
        response.ok = True
        mock_post.return_value = response

        client = NtfyClient('https://ntfy.sh', 'alerts')
        client.publish(
            'Job finished',
            title='SuggestArr: Job completed',
            priority=3,
            tags=['white_check_mark', 'suggestarr'],
        )

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], 'https://ntfy.sh/alerts')
        self.assertEqual(kwargs['data'], b'Job finished')
        self.assertEqual(kwargs['headers']['Title'], 'SuggestArr: Job completed')
        self.assertEqual(kwargs['headers']['Priority'], '3')
        self.assertEqual(kwargs['headers']['Tags'], 'white_check_mark,suggestarr')
        self.assertIsNone(kwargs['auth'])
        self.assertEqual(kwargs['timeout'], 10)

    @patch('api_service.services.notifications.ntfy_client.requests.post')
    def test_publish_uses_bearer_token(self, mock_post):
        response = MagicMock()
        response.ok = True
        mock_post.return_value = response

        client = NtfyClient(
            'https://ntfy.example.com',
            'private',
            access_token='tok123',
        )
        client.publish('hello', title='Hi', priority=3, tags=[])

        headers = mock_post.call_args.kwargs['headers']
        self.assertEqual(headers['Authorization'], 'Bearer tok123')

    @patch('api_service.services.notifications.ntfy_client.requests.post')
    def test_publish_uses_basic_auth(self, mock_post):
        response = MagicMock()
        response.ok = True
        mock_post.return_value = response

        client = NtfyClient(
            'http://192.168.40.12:80',
            'arr',
            username='admin',
            password='secret',
        )
        client.publish('hello', title='Hi', priority=4, tags=['x'])

        auth = mock_post.call_args.kwargs['auth']
        self.assertEqual(auth.username, 'admin')
        self.assertEqual(auth.password, 'secret')

    @patch('api_service.services.notifications.ntfy_client.requests.post')
    def test_publish_custom_timeout(self, mock_post):
        response = MagicMock()
        response.ok = True
        mock_post.return_value = response

        client = NtfyClient('https://ntfy.sh', 't', timeout=5)
        client.publish('x', title='T', priority=3, tags=[])

        self.assertEqual(mock_post.call_args.kwargs['timeout'], 5)

    @patch('api_service.services.notifications.ntfy_client.requests.post')
    def test_publish_non_2xx_raises(self, mock_post):
        response = MagicMock()
        response.ok = False
        response.status_code = 403
        response.reason = 'Forbidden'
        response.text = 'not allowed'
        mock_post.return_value = response

        client = NtfyClient('https://ntfy.sh', 'secret')
        with self.assertRaises(NtfyPublishError) as ctx:
            client.publish('fail', title='T', priority=3, tags=[])

        self.assertIn('403', str(ctx.exception))
        self.assertIn('not allowed', str(ctx.exception))

    @patch('api_service.services.notifications.ntfy_client.requests.post')
    def test_publish_network_error_raises(self, mock_post):
        mock_post.side_effect = requests.Timeout('timed out')

        client = NtfyClient('https://ntfy.sh', 't')
        with self.assertRaises(NtfyPublishError) as ctx:
            client.publish('x', title='T', priority=3, tags=[])

        self.assertIn('timed out', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
