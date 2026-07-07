"""Tests for job execution end notification hook."""

import os
import tempfile
import unittest
from unittest.mock import patch

import api_service.db.database_manager as dm_mod
from api_service.db.database_manager import DatabaseManager
from api_service.db.job_repository import JobRepository


class TestJobRepositoryNotifications(unittest.TestCase):
    def setUp(self):
        DatabaseManager._instance = None
        fd, self.db_file = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        self.path_patch = patch.object(dm_mod, 'DB_PATH', self.db_file)
        self.env_patch = patch(
            'api_service.db.database_manager.load_env_vars',
            return_value={'DB_TYPE': 'sqlite'},
        )
        self.path_patch.start()
        self.env_patch.start()
        self.db = DatabaseManager()
        self.repository = JobRepository()

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO discover_jobs (
                    name, job_type, enabled, media_type, filters,
                    schedule_type, schedule_value, pause_if_pending_requests
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ('Daily', 'discover', 1, 'movie', '{}', 'cron', '0 0 * * *', 0),
            )
            conn.commit()
            cursor.execute('SELECT id FROM discover_jobs LIMIT 1')
            self.job_id = cursor.fetchone()[0]

    def tearDown(self):
        DatabaseManager._instance = None
        self.env_patch.stop()
        self.path_patch.stop()
        try:
            os.unlink(self.db_file)
        except FileNotFoundError:
            pass

    @patch('api_service.services.notifications.notification_service.NotificationService')
    def test_log_execution_end_notifies_completed(self, mock_service_cls):
        exec_id = self.repository.log_execution_start(self.job_id)
        self.repository.log_execution_end(
            exec_id,
            status='completed',
            results_count=4,
            requested_count=2,
        )

        mock_service_cls.return_value.notify_execution_end.assert_called_once_with(
            exec_id,
            'completed',
            results_count=4,
            requested_count=2,
            error_message=None,
        )


if __name__ == '__main__':
    unittest.main()
