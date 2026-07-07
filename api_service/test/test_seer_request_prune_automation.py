"""Tests for Seer request prune automation."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api_service.jobs import seer_request_prune_automation as prune


@pytest.mark.asyncio
async def test_execute_prune_skips_when_disabled():
    db = MagicMock()
    db.get_seer_request_prune_settings.return_value = {"enabled": False, "dry_run": True}

    with patch.object(prune, "DatabaseManager", return_value=db):
        result = await prune.execute_seer_request_prune_job()

    assert result["status"] == "skipped"


@pytest.mark.asyncio
async def test_execute_prune_dry_run_logs_candidates():
    now = datetime.utcnow()
    old = (now - timedelta(days=20)).isoformat() + "Z"
    db = MagicMock()
    db.get_seer_request_prune_settings.return_value = {
        "enabled": True,
        "dry_run": True,
        "sync_suggestarr": False,
        "declined_days": 14,
        "failed_days": 7,
        "completed_days": 7,
        "deleted_days": 3,
    }

    client = MagicMock()
    client.get_requests_index = AsyncMock(return_value={
        ("movie", "123"): [{
            "id": 9,
            "status": 3,
            "media_status": 2,
            "updated_at": old,
            "title": "Old Declined",
        }],
    })
    client.close = AsyncMock()
    client.delete_request = AsyncMock(return_value=True)

    with patch.object(prune, "DatabaseManager", return_value=db), \
            patch.object(prune, "ConfigService") as config_service, \
            patch.object(prune, "SeerClient", return_value=client), \
            patch.object(prune, "invalidate_requests_index_cache"):
        config_service.get_runtime_config.return_value = {
            "SEER_API_URL": "http://seer.local",
            "SEER_TOKEN": "token",
        }
        result = await prune.execute_seer_request_prune_job(force_run=True)

    assert result["status"] == "ok"
    assert result["would_delete"] == 1
    client.delete_request.assert_not_called()
    db.add_seer_request_prune_log.assert_called_once()
    assert db.add_seer_request_prune_log.call_args.kwargs["action"] == "would_delete"


@pytest.mark.asyncio
async def test_execute_prune_deletes_and_syncs_suggestarr():
    now = datetime.utcnow()
    old = (now - timedelta(days=20)).isoformat() + "Z"
    db = MagicMock()
    db.get_seer_request_prune_settings.return_value = {
        "enabled": True,
        "dry_run": False,
        "sync_suggestarr": True,
        "declined_days": 14,
        "failed_days": 7,
        "completed_days": 7,
        "deleted_days": 3,
    }

    client = MagicMock()
    client.get_requests_index = AsyncMock(return_value={
        ("tv", "55"): [{
            "id": 11,
            "status": 3,
            "media_status": 2,
            "updated_at": old,
            "title": "Old Show",
        }],
    })
    client.close = AsyncMock()
    client.delete_request = AsyncMock(return_value=True)

    with patch.object(prune, "DatabaseManager", return_value=db), \
            patch.object(prune, "ConfigService") as config_service, \
            patch.object(prune, "SeerClient", return_value=client), \
            patch.object(prune, "invalidate_requests_index_cache"):
        config_service.get_runtime_config.return_value = {
            "SEER_API_URL": "http://seer.local",
            "SEER_TOKEN": "token",
        }
        result = await prune.execute_seer_request_prune_job(force_run=True, override_dry_run=False)

    assert result["deleted"] == 1
    assert result["synced_suggestarr"] == 1
    client.delete_request.assert_awaited_once_with(11)
    db.delete_request_row.assert_called_once_with("55", "tv")
