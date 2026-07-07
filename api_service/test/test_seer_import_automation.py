"""Tests for Seer request import automation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api_service.jobs import seer_import_automation as import_job
from api_service.services.request_sources import SEER_IMPORT_SOURCE


@pytest.mark.asyncio
async def test_execute_import_skips_when_disabled():
    db = MagicMock()
    db.get_seer_import_settings.return_value = {"enabled": False, "dry_run": True}

    with patch.object(import_job, "DatabaseManager", return_value=db):
        result = await import_job.execute_seer_import_job()

    assert result["status"] == "skipped"


@pytest.mark.asyncio
async def test_execute_import_dry_run_logs_new_candidates():
    db = MagicMock()
    db.get_seer_import_settings.return_value = {"enabled": True, "dry_run": True, "status_filter": "all"}
    db.get_suggestarr_request_keys.return_value = set()
    db.get_legacy_seer_request_keys.return_value = set()

    client = MagicMock()
    client.get_requests_index = AsyncMock(return_value={
        ("movie", "123"): [{
            "id": 1,
            "status": 1,
            "media_status": 2,
            "created_at": "2024-01-01T00:00:00.000Z",
            "updated_at": "2024-01-02T00:00:00.000Z",
            "title": "Example Movie",
        }],
    })
    client.close = AsyncMock()

    with patch.object(import_job, "DatabaseManager", return_value=db), \
            patch.object(import_job, "ConfigService") as config_service, \
            patch.object(import_job, "SeerClient", return_value=client), \
            patch.object(import_job, "invalidate_requests_index_cache"):
        config_service.get_runtime_config.return_value = {
            "SEER_API_URL": "http://seer.local",
            "SEER_TOKEN": "token",
        }
        result = await import_job.execute_seer_import_job(force_run=True)

    assert result["status"] == "ok"
    assert result["would_import"] == 1
    db.save_request.assert_not_called()
    db.adopt_legacy_seer_request_row.assert_not_called()


@pytest.mark.asyncio
async def test_execute_import_adopts_legacy_seer_rows():
    db = MagicMock()
    db.get_seer_import_settings.return_value = {"enabled": True, "dry_run": False, "status_filter": "all"}
    db.get_suggestarr_request_keys.return_value = set()
    db.get_legacy_seer_request_keys.return_value = {("tv", "55")}

    client = MagicMock()
    client.get_requests_index = AsyncMock(return_value={
        ("tv", "55"): [{
            "id": 9,
            "status": 2,
            "media_status": 3,
            "created_at": "2024-02-01T00:00:00.000Z",
            "updated_at": "2024-02-02T00:00:00.000Z",
            "title": "Example Show",
        }],
    })
    client.get_media_details = AsyncMock(return_value={
        "available": True,
        "tmdb_id": "55",
        "media_type": "tv",
        "title": "Example Show",
    })
    client.close = AsyncMock()

    with patch.object(import_job, "DatabaseManager", return_value=db), \
            patch.object(import_job, "ConfigService") as config_service, \
            patch.object(import_job, "SeerClient", return_value=client), \
            patch.object(import_job, "invalidate_requests_index_cache"):
        config_service.get_runtime_config.return_value = {
            "SEER_API_URL": "http://seer.local",
            "SEER_TOKEN": "token",
        }
        result = await import_job.execute_seer_import_job(force_run=True, override_dry_run=False)

    assert result["adopted"] == 1
    assert result["imported"] == 0
    db.adopt_legacy_seer_request_row.assert_called_once()
    db.update_request_seer_state.assert_called_once_with(
        "55",
        "tv",
        seer_request_id=9,
        seer_request_status=2,
        seer_media_status=3,
        seer_status="processing",
        seer_updated_at="2024-02-02 00:00:00",
    )
    db.save_request.assert_not_called()


@pytest.mark.asyncio
async def test_execute_import_writes_new_request_and_metadata():
    db = MagicMock()
    db.get_seer_import_settings.return_value = {"enabled": True, "dry_run": False, "status_filter": "all"}
    db.get_suggestarr_request_keys.return_value = set()
    db.get_legacy_seer_request_keys.return_value = set()

    client = MagicMock()
    client.get_requests_index = AsyncMock(return_value={
        ("tv", "55"): [{
            "id": 9,
            "status": 2,
            "media_status": 3,
            "created_at": "2024-02-01T00:00:00.000Z",
            "updated_at": "2024-02-02T00:00:00.000Z",
            "title": "Example Show",
        }],
    })
    client.get_media_details = AsyncMock(return_value={
        "available": True,
        "tmdb_id": "55",
        "media_type": "tv",
        "title": "Example Show",
    })
    client.close = AsyncMock()

    with patch.object(import_job, "DatabaseManager", return_value=db), \
            patch.object(import_job, "ConfigService") as config_service, \
            patch.object(import_job, "SeerClient", return_value=client), \
            patch.object(import_job, "invalidate_requests_index_cache"):
        config_service.get_runtime_config.return_value = {
            "SEER_API_URL": "http://seer.local",
            "SEER_TOKEN": "token",
        }
        result = await import_job.execute_seer_import_job(force_run=True, override_dry_run=False)

    assert result["imported"] == 1
    db.save_request.assert_called_once()
    args = db.save_request.call_args
    assert args.args[2] == SEER_IMPORT_SOURCE
    db.update_request_seer_state.assert_called_once_with(
        "55",
        "tv",
        seer_request_id=9,
        seer_request_status=2,
        seer_media_status=3,
        seer_status="processing",
        seer_updated_at="2024-02-02 00:00:00",
    )


@pytest.mark.asyncio
async def test_execute_import_refreshes_existing_rows():
    db = MagicMock()
    db.get_seer_import_settings.return_value = {"enabled": True, "dry_run": False, "status_filter": "all"}
    db.get_suggestarr_request_keys.return_value = {("movie", "123")}
    db.get_legacy_seer_request_keys.return_value = set()

    client = MagicMock()
    client.get_requests_index = AsyncMock(return_value={
        ("movie", "123"): [{
            "id": 44,
            "status": 3,
            "media_status": 6,
            "created_at": "2024-01-01T00:00:00.000Z",
            "updated_at": "2024-01-04T00:00:00.000Z",
            "title": "Existing Movie",
        }],
    })
    client.close = AsyncMock()

    with patch.object(import_job, "DatabaseManager", return_value=db), \
            patch.object(import_job, "ConfigService") as config_service, \
            patch.object(import_job, "SeerClient", return_value=client), \
            patch.object(import_job, "invalidate_requests_index_cache"):
        config_service.get_runtime_config.return_value = {
            "SEER_API_URL": "http://seer.local",
            "SEER_TOKEN": "token",
        }
        result = await import_job.execute_seer_import_job(force_run=True, override_dry_run=False)

    assert result["refreshed"] == 1
    assert result["skipped"] == 0
    db.update_request_seer_state.assert_called_once_with(
        "123",
        "movie",
        seer_request_id=44,
        seer_request_status=3,
        seer_media_status=6,
        seer_status="declined",
        seer_updated_at="2024-01-04 00:00:00",
    )


@pytest.mark.asyncio
async def test_execute_import_pending_filter_skips_settled_requests():
    db = MagicMock()
    db.get_seer_import_settings.return_value = {"enabled": True, "dry_run": True, "status_filter": "pending"}
    db.get_suggestarr_request_keys.return_value = set()
    db.get_legacy_seer_request_keys.return_value = set()

    client = MagicMock()
    client.get_requests_index = AsyncMock(return_value={
        ("movie", "123"): [{
            "id": 1,
            "status": 1,
            "media_status": 2,
            "created_at": "2024-01-01T00:00:00.000Z",
            "updated_at": "2024-01-01T00:00:00.000Z",
            "title": "Pending Movie",
        }],
        ("movie", "456"): [{
            "id": 2,
            "status": 3,
            "media_status": 2,
            "created_at": "2024-01-01T00:00:00.000Z",
            "updated_at": "2024-01-01T00:00:00.000Z",
            "title": "Declined Movie",
        }],
    })
    client.close = AsyncMock()

    with patch.object(import_job, "DatabaseManager", return_value=db), \
            patch.object(import_job, "ConfigService") as config_service, \
            patch.object(import_job, "SeerClient", return_value=client), \
            patch.object(import_job, "invalidate_requests_index_cache"):
        config_service.get_runtime_config.return_value = {
            "SEER_API_URL": "http://seer.local",
            "SEER_TOKEN": "token",
        }
        result = await import_job.execute_seer_import_job(force_run=True)

    assert result["would_import"] == 1
    assert result["filtered"] == 1


def test_collect_import_candidates_deduplicates_media_keys():
    index = {
        ("movie", "1"): [
            {"id": 1, "status": 1, "media_status": 2, "title": "A", "created_at": "2024-01-01T00:00:00.000Z"},
            {"id": 2, "status": 1, "media_status": 2, "title": "A", "created_at": "2024-01-03T00:00:00.000Z"},
        ],
    }
    candidates = import_job._collect_import_candidates(index)
    assert len(candidates) == 1
    assert candidates[0]["tmdb_id"] == "1"
    assert candidates[0]["seer_request_count"] == 2
