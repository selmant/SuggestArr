from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api_service.services.seer import request_actions


class FakeSeerClient:
    instances = []
    decline_should_fail = False

    def __init__(self, api_url, api_key, session_token=None, **kwargs):
        self.api_url = api_url
        self.api_key = api_key
        self.session_token = session_token
        self.index = {}
        self.approve_request = AsyncMock(return_value=True)
        self.decline_request = AsyncMock(side_effect=self._decline_side_effect)
        FakeSeerClient.instances.append(self)

    async def _decline_side_effect(self, request_id):
        if FakeSeerClient.decline_should_fail:
            return False
        return True

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get_requests_index(self):
        return self.index


def _configured_env():
    return {
        "SEER_API_URL": "http://seer.local",
        "SEER_TOKEN": "token",
        "integrations": {
            "seer": {
                "api_url": "http://seer.local",
                "api_key": "token",
            },
        },
    }


@pytest.mark.asyncio
async def test_get_request_seer_status_returns_pending_payload():
    db = MagicMock()
    FakeSeerClient.instances = []
    client = FakeSeerClient("http://seer.local", "token")
    client.index = {
        ("movie", "123"): [{"id": 9, "status": 1, "media_status": 2}],
    }

    with patch.object(request_actions, "SeerClient", FakeSeerClient), \
            patch.object(request_actions, "load_env_vars", return_value=_configured_env()), \
            patch.object(request_actions, "_get_requests_index", AsyncMock(return_value=client.index)):
        result = await request_actions.get_request_seer_status(db, "123", "movie")

    assert result["seer_status"] == "pending"
    assert result["can_action"] is True
    assert result["seer_request_ids"] == [9]


@pytest.mark.asyncio
async def test_get_request_seer_status_returns_not_found_when_missing():
    db = MagicMock()

    with patch.object(request_actions, "SeerClient", FakeSeerClient), \
            patch.object(request_actions, "load_env_vars", return_value=_configured_env()), \
            patch.object(request_actions, "_get_requests_index", AsyncMock(return_value={})):
        result = await request_actions.get_request_seer_status(db, "999", "tv")

    assert result["seer_status"] == "not_found"
    assert result["can_action"] is False
    assert result["seer_request_ids"] == []


@pytest.mark.asyncio
async def test_get_request_seer_statuses_batch_maps_many_items():
    db = MagicMock()
    index = {
        ("movie", "1"): [{"id": 1, "status": 2, "media_status": 5}],
        ("tv", "2"): [{"id": 2, "status": 1, "media_status": 2}],
    }

    with patch.object(request_actions, "SeerClient", FakeSeerClient), \
            patch.object(request_actions, "load_env_vars", return_value=_configured_env()), \
            patch.object(request_actions, "_get_requests_index", AsyncMock(return_value=index)):
        result = await request_actions.get_request_seer_statuses_batch(
            db,
            [
                {"tmdb_id": "1", "media_type": "movie"},
                {"request_id": "2", "media_type": "tv"},
            ],
        )

    assert len(result["statuses"]) == 2
    assert result["statuses"][0]["seer_status"] == "available"
    assert result["statuses"][1]["seer_status"] == "pending"


@pytest.mark.asyncio
async def test_approve_request_acts_on_all_pending_matches():
    db = MagicMock()
    FakeSeerClient.instances = []
    FakeSeerClient.decline_should_fail = False
    index_state = {
        ("tv", "55"): [
            {"id": 10, "status": 1, "media_status": 2},
            {"id": 11, "status": 1, "media_status": 2},
        ],
    }
    call_count = {"force": 0}

    async def refresh_index(client, *, force=False):
        if force:
            call_count["force"] += 1
            if call_count["force"] >= 2:
                index_state[("tv", "55")] = [
                    {"id": 10, "status": 2, "media_status": 3},
                    {"id": 11, "status": 2, "media_status": 3},
                ]
        return index_state

    with patch.object(request_actions, "SeerClient", FakeSeerClient), \
            patch.object(request_actions, "load_env_vars", return_value=_configured_env()), \
            patch.object(request_actions, "_get_requests_index", side_effect=refresh_index):
        result = await request_actions.approve_request(db, "55", "tv")

    active_client = FakeSeerClient.instances[-1]
    assert active_client.approve_request.await_count == 2
    active_client.approve_request.assert_any_await(10)
    active_client.approve_request.assert_any_await(11)
    assert result["seer_status"] == "processing"
    assert result["can_action"] is False


@pytest.mark.asyncio
async def test_decline_request_raises_when_seer_call_fails():
    db = MagicMock()
    FakeSeerClient.instances = []
    FakeSeerClient.decline_should_fail = True
    index = {
        ("movie", "7"): [{"id": 3, "status": 1, "media_status": 2}],
    }

    with patch.object(request_actions, "SeerClient", FakeSeerClient), \
            patch.object(request_actions, "load_env_vars", return_value=_configured_env()), \
            patch.object(request_actions, "_get_requests_index", AsyncMock(return_value=index)):
        with pytest.raises(RuntimeError, match="could not decline"):
            await request_actions.decline_request(db, "7", "movie")


def test_derive_seer_status_maps_media_states():
    assert request_actions._derive_seer_status(1, 2) == "pending"
    assert request_actions._derive_seer_status(3, 2) == "declined"
    assert request_actions._derive_seer_status(2, 5) == "available"
    assert request_actions._derive_seer_status(2, 4) == "partially_available"
    assert request_actions._derive_seer_status(2, 3) == "processing"
    assert request_actions._derive_seer_status(2, 2) == "approved"
