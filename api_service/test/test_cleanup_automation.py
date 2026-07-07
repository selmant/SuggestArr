import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from api_service.jobs import cleanup_automation


class TestCleanupAutomationCutoff(unittest.IsolatedAsyncioTestCase):
    async def test_cleanup_cutoff_uses_current_timestamp_format(self):
        class FakeDB:
            cutoff = None
            updates = []

            def get_cleanup_settings(self):
                return {"enabled": True, "dry_run": True, "grace_days": 1}

            def get_suggestarr_requests_older_than(self, cutoff):
                FakeDB.cutoff = cutoff
                return []

            def update_cleanup_settings(self, **kwargs):
                FakeDB.updates.append(kwargs)

        fixed_now = datetime(2026, 5, 25, 12, 34, 56)

        class FixedDatetime:
            @staticmethod
            def utcnow():
                return fixed_now

        with patch.object(cleanup_automation, "DatabaseManager", return_value=FakeDB()), \
             patch.object(cleanup_automation.ConfigService, "get_runtime_config", return_value={
                 "SELECTED_SERVICE": "plex",
                 "PLEX_API_URL": "http://plex.local",
                 "PLEX_TOKEN": "token",
             }), \
             patch.object(cleanup_automation, "datetime", FixedDatetime):
            result = await cleanup_automation.execute_cleanup_job()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(FakeDB.cutoff, "2026-05-24 12:34:56")
        self.assertNotIn("T", FakeDB.cutoff)
        self.assertEqual(FakeDB.updates[-1]["last_run_at"], "2026-05-25 12:34:56")


class TestCleanupAutomationDeclineArchive(unittest.IsolatedAsyncioTestCase):
    async def test_real_cleanup_declines_pending_and_archives_suggestarr_row(self):
        class FakeDB:
            archived_rows = []
            log_actions = []
            updates = []

            def get_cleanup_settings(self):
                return {"enabled": True, "dry_run": False, "grace_days": 7}

            def get_suggestarr_requests_older_than(self, cutoff):
                return [{
                    "tmdb_id": "55",
                    "media_type": "tv",
                    "requested_at": "2026-05-01 00:00:00",
                    "title": "Old Show",
                }]

            def archive_request_row(self, tmdb_id, media_type, reason='grace_cleanup'):
                FakeDB.archived_rows.append((tmdb_id, media_type, reason))
                return 1

            def update_request_seer_state(self, *args, **kwargs):
                return None

            def add_cleanup_log(self, **kwargs):
                FakeDB.log_actions.append(kwargs["action"])

            def update_cleanup_settings(self, **kwargs):
                FakeDB.updates.append(kwargs)

        class FakeSeerClient:
            instances = []

            def __init__(self, *args, **kwargs):
                self.decline_request = AsyncMock(return_value=True)
                self.get_requests_index = AsyncMock(return_value={
                    ("tv", "55"): [{"id": 123, "status": 1, "media_status": 2}],
                })
                self.close = AsyncMock()
                FakeSeerClient.instances.append(self)

        with patch.object(cleanup_automation, "DatabaseManager", return_value=FakeDB()), \
             patch.object(cleanup_automation.ConfigService, "get_runtime_config", return_value={
                 "SELECTED_SERVICE": "plex",
                 "PLEX_API_URL": "http://plex.local",
                 "PLEX_TOKEN": "token",
                 "SEER_API_URL": "http://seer.local",
                 "SEER_TOKEN": "seer-token",
             }), \
             patch.object(cleanup_automation, "_build_favorite_map", AsyncMock(return_value={("tv", "55"): 0.0})), \
             patch.object(cleanup_automation, "SeerClient", FakeSeerClient):
            result = await cleanup_automation.execute_cleanup_job()

        client = FakeSeerClient.instances[0]
        client.get_requests_index.assert_awaited_once()
        client.decline_request.assert_awaited_once_with(123)
        self.assertEqual(FakeDB.archived_rows, [("55", "tv", "grace_cleanup")])
        self.assertIn("declined", FakeDB.log_actions)
        self.assertIn("archived", FakeDB.log_actions)
        self.assertEqual(result["declined"], 1)
        self.assertEqual(result["archived"], 1)

    async def test_cleanup_skips_seer_decline_when_not_pending_but_still_archives(self):
        class FakeDB:
            log_actions = []

            def get_cleanup_settings(self):
                return {"enabled": True, "dry_run": False, "grace_days": 7}

            def get_suggestarr_requests_older_than(self, cutoff):
                return [{
                    "tmdb_id": "77",
                    "media_type": "movie",
                    "requested_at": "2026-05-01 00:00:00",
                    "title": "Settled Movie",
                }]

            def archive_request_row(self, tmdb_id, media_type, reason='grace_cleanup'):
                return 1

            def update_request_seer_state(self, *args, **kwargs):
                return None

            def add_cleanup_log(self, **kwargs):
                FakeDB.log_actions.append(kwargs["action"])

            def update_cleanup_settings(self, **kwargs):
                pass

        class FakeSeerClient:
            instances = []

            def __init__(self, *args, **kwargs):
                self.decline_request = AsyncMock(return_value=True)
                self.get_requests_index = AsyncMock(return_value={
                    ("movie", "77"): [{"id": 456, "status": 3, "media_status": 5}],
                })
                self.close = AsyncMock()
                FakeSeerClient.instances.append(self)

        with patch.object(cleanup_automation, "DatabaseManager", return_value=FakeDB()), \
             patch.object(cleanup_automation.ConfigService, "get_runtime_config", return_value={
                 "SELECTED_SERVICE": "jellyfin",
                 "JELLYFIN_API_URL": "http://jellyfin.local",
                 "JELLYFIN_TOKEN": "token",
                 "SEER_API_URL": "http://seer.local",
                 "SEER_TOKEN": "seer-token",
             }), \
             patch.object(cleanup_automation, "_build_favorite_map", AsyncMock(return_value={})), \
             patch.object(cleanup_automation, "SeerClient", FakeSeerClient):
            result = await cleanup_automation.execute_cleanup_job()

        FakeSeerClient.instances[0].decline_request.assert_not_awaited()
        self.assertIn("skipped_not_pending", FakeDB.log_actions)
        self.assertIn("archived", FakeDB.log_actions)
        self.assertEqual(result["declined"], 0)
        self.assertEqual(result["archived"], 1)

    async def test_dry_run_logs_would_decline_and_would_archive(self):
        class FakeDB:
            log_actions = []

            def get_cleanup_settings(self):
                return {"enabled": True, "dry_run": True, "grace_days": 7}

            def get_suggestarr_requests_older_than(self, cutoff):
                return [{
                    "tmdb_id": "99",
                    "media_type": "movie",
                    "requested_at": "2026-05-01 00:00:00",
                    "title": "Pending Movie",
                }]

            def add_cleanup_log(self, **kwargs):
                FakeDB.log_actions.append(kwargs["action"])

            def update_cleanup_settings(self, **kwargs):
                pass

        class FakeSeerClient:
            instances = []

            def __init__(self, *args, **kwargs):
                self.get_requests_index = AsyncMock(return_value={
                    ("movie", "99"): [{"id": 456, "status": 1, "media_status": 2}],
                })
                self.close = AsyncMock()
                FakeSeerClient.instances.append(self)

        with patch.object(cleanup_automation, "DatabaseManager", return_value=FakeDB()), \
             patch.object(cleanup_automation.ConfigService, "get_runtime_config", return_value={
                 "SELECTED_SERVICE": "jellyfin",
                 "JELLYFIN_API_URL": "http://jellyfin.local",
                 "JELLYFIN_TOKEN": "token",
                 "SEER_API_URL": "http://seer.local",
                 "SEER_TOKEN": "seer-token",
             }), \
             patch.object(cleanup_automation, "_build_favorite_map", AsyncMock(return_value={})), \
             patch.object(cleanup_automation, "SeerClient", FakeSeerClient):
            result = await cleanup_automation.execute_cleanup_job()

        self.assertEqual(result["declined"], 1)
        self.assertEqual(result["archived"], 1)
        self.assertEqual(FakeDB.log_actions, ["would_decline", "would_archive"])


if __name__ == "__main__":
    unittest.main()
