"""Tests for discover job request routing."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from api_service.jobs.discover_automation import DiscoverAutomation


@pytest.mark.asyncio
async def test_filter_and_request_passes_anime_flag_to_seer():
    automation = DiscoverAutomation()
    automation.job_data = {"media_type": "movie"}
    automation.db_manager = MagicMock()
    automation.db_manager.check_request_exists.return_value = False
    automation.seer_client = MagicMock()
    automation.seer_client.check_already_downloaded = AsyncMock(return_value=False)
    automation.seer_client.check_already_requested = AsyncMock(return_value=False)
    automation.seer_client.request_media = AsyncMock(return_value=True)

    requested_count, dry_run_items = await automation.filter_and_request([
        {
            "id": 101,
            "title": "Anime Movie",
            "genre_ids": [16],
            "original_language": "ja",
            "origin_country": ["JP"],
        },
    ])

    assert requested_count == 1
    assert dry_run_items is None
    automation.seer_client.request_media.assert_awaited_once_with(
        "movie",
        {
            "id": 101,
            "title": "Anime Movie",
            "genre_ids": [16],
            "original_language": "ja",
            "origin_country": ["JP"],
        },
        source={"id": "discover"},
        user=None,
        is_anime=True,
    )
