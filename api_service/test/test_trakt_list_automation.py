"""Tests for Trakt list job automation."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api_service.jobs.trakt_list_automation import TraktListAutomation


@pytest.mark.asyncio
async def test_create_rejects_non_trakt_list_job():
    with patch("api_service.jobs.trakt_list_automation.JobRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.get_job.return_value = {"id": 1, "job_type": "discover", "name": "Wrong"}

        with pytest.raises(ValueError, match="not a trakt_list job"):
            await TraktListAutomation.create(1)


@pytest.mark.asyncio
async def test_filter_and_request_global_dedup_skips_existing_requests():
    automation = TraktListAutomation()
    automation.job_id = 7
    automation.job_data = {"filters": {"dedup_mode": "global"}, "media_type": "movie"}
    automation.db_manager = MagicMock()
    automation.seer_client = AsyncMock()
    automation._should_skip_global_request = AsyncMock(return_value=True)

    requested_count, _ = await automation.filter_and_request([
        {"id": 1, "title": "Heat", "media_type": "movie"},
    ])

    assert requested_count == 0
    automation.seer_client.request_media.assert_not_awaited()


@pytest.mark.asyncio
async def test_filter_and_request_per_list_dedup_marks_seen_items():
    automation = TraktListAutomation()
    automation.job_id = 7
    automation.job_data = {"filters": {"dedup_mode": "per_list"}, "media_type": "movie"}
    automation.db_manager = MagicMock()
    automation.db_manager.get_trakt_list_seen.return_value = {("1", "movie")}
    automation.seer_client = AsyncMock()
    automation.seer_client.request_media.return_value = True

    requested_count, _ = await automation.filter_and_request([
        {"id": 1, "title": "Seen", "media_type": "movie"},
        {"id": 2, "title": "New", "media_type": "movie"},
    ])

    assert requested_count == 1
    automation.seer_client.request_media.assert_awaited_once()
    automation.db_manager.mark_trakt_list_seen.assert_called_once_with(
        7,
        [("2", "movie")],
    )


@pytest.mark.asyncio
async def test_filter_and_request_passes_anime_flag_to_seer():
    automation = TraktListAutomation()
    automation.job_id = 7
    automation.job_data = {"filters": {"dedup_mode": "global"}, "media_type": "movie"}
    automation.db_manager = MagicMock()
    automation.seer_client = AsyncMock()
    automation.seer_client.request_media.return_value = True
    automation._should_skip_global_request = AsyncMock(return_value=False)

    requested_count, _ = await automation.filter_and_request([
        {
            "id": 1,
            "title": "Anime Film",
            "media_type": "movie",
            "genre_ids": [16],
            "original_language": "ja",
            "origin_country": ["JP"],
        },
    ])

    assert requested_count == 1
    automation.seer_client.request_media.assert_awaited_once_with(
        "movie",
        {
            "id": 1,
            "title": "Anime Film",
            "media_type": "movie",
            "genre_ids": [16],
            "original_language": "ja",
            "origin_country": ["JP"],
        },
        source={"id": "trakt_list"},
        user=None,
        is_anime=True,
    )


@pytest.mark.asyncio
async def test_initialize_components_disables_global_exclude_requested_for_per_list():
    automation = TraktListAutomation()
    automation.job_data = {
        "filters": {"dedup_mode": "per_list", "list_source": "public_url", "list_url": "sean/horror"},
        "media_type": "movie",
        "user_ids": [],
    }
    automation.env_vars = {
        "SEER_API_URL": "http://seer",
        "SEER_TOKEN": "token",
        "SEER_USER_NAME": "user",
        "SEER_USER_PSW": "pass",
        "SEER_SESSION_TOKEN": "session",
        "TMDB_API_KEY": "tmdb",
        "SELECTED_SERVICE": "jellyfin",
        "EXCLUDE_REQUESTED": True,
    }
    automation._initialize_shared_components = AsyncMock()
    automation._build_trakt_client_and_list_target = MagicMock(return_value=(
        MagicMock(), "sean", "horror", False, False
    ))

    async def _init_shared(dry_run=False):
        automation.seer_client = MagicMock()
        automation.seer_client.exclude_requested = True

    automation._initialize_shared_components = AsyncMock(side_effect=_init_shared)

    await automation._initialize_components()

    assert automation.seer_client.exclude_requested is False


@pytest.mark.asyncio
async def test_fetch_list_items_uses_watchlist_when_configured():
    automation = TraktListAutomation()
    automation.job_data = {"media_type": "movie", "max_results": 5}
    automation.use_watchlist = True
    automation.list_user = "me"
    automation.authenticated = True
    automation.trakt_client = AsyncMock()

    async def watchlist_side_effect(*args, **kwargs):
        page = kwargs.get("page", 1)
        if page == 1:
            return [{"tmdb_id": "1", "title": "One", "media_type": "movie"}]
        return []

    automation.trakt_client.get_watchlist_items.side_effect = watchlist_side_effect
    automation._should_skip_fetch_item = AsyncMock(return_value=False)
    automation._enrich_and_filter_item = AsyncMock(side_effect=lambda item: {
        "id": int(item["tmdb_id"]),
        "title": item["title"],
        "media_type": item["media_type"],
    })

    results = await automation.fetch_list_items()

    assert len(results) == 1
    automation.trakt_client.get_watchlist_items.assert_any_await(
        "me",
        "movie",
        limit=100,
        page=1,
        authenticated=True,
    )
    assert automation.trakt_client.get_watchlist_items.await_count == 2


@pytest.mark.asyncio
async def test_fetch_list_items_paginates_past_already_requested_items():
    automation = TraktListAutomation()
    automation.job_id = 7
    automation.job_data = {
        "media_type": "movie",
        "max_results": 1,
        "filters": {"dedup_mode": "global"},
    }
    automation.use_watchlist = False
    automation.list_user = "sean"
    automation.list_ref = "horror"
    automation.authenticated = False
    automation.trakt_client = AsyncMock()

    async def get_list_items_side_effect(*args, **kwargs):
        page = kwargs.get("page", 1)
        if page == 1:
            return [{"tmdb_id": "1", "title": "Old", "media_type": "movie"}]
        if page == 2:
            return [{"tmdb_id": "2", "title": "New", "media_type": "movie"}]
        return []

    automation.trakt_client.get_list_items.side_effect = get_list_items_side_effect

    async def skip_fetch_item(media_type, tmdb_id, dedup_mode, per_list_seen):
        return str(tmdb_id) == "1"

    automation._should_skip_fetch_item = AsyncMock(side_effect=skip_fetch_item)
    automation._enrich_and_filter_item = AsyncMock(side_effect=lambda item: {
        "id": int(item["tmdb_id"]),
        "title": item["title"],
        "media_type": item["media_type"],
    })

    results = await automation.fetch_list_items()

    assert len(results) == 1
    assert results[0]["id"] == 2
    assert automation.trakt_client.get_list_items.await_count == 3
    automation._enrich_and_filter_item.assert_awaited_once()
