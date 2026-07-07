"""Tests for shared Seer status helpers."""

import pytest

from api_service.services.seer import seer_status


def test_derive_seer_status_maps_core_states():
    assert seer_status.derive_seer_status(1, 2) == "pending"
    assert seer_status.derive_seer_status(3, 2) == "declined"
    assert seer_status.derive_seer_status(4, 2) == "failed"
    assert seer_status.derive_seer_status(5, 2) == "completed"
    assert seer_status.derive_seer_status(2, 5) == "available"
    assert seer_status.derive_seer_status(2, 4) == "partially_available"
    assert seer_status.derive_seer_status(2, 3) == "processing"
    assert seer_status.derive_seer_status(2, 6) == "deleted"
    assert seer_status.derive_seer_status(2, 1) == "unavailable"


def test_matches_seer_status_filter_supports_composites():
    assert seer_status.matches_seer_status_filter("pending", "unavailable") is True
    assert seer_status.matches_seer_status_filter("processing", "processing") is True
    assert seer_status.matches_seer_status_filter("available", "unavailable") is False
    assert seer_status.matches_seer_status_filter("failed", "failed") is True


def test_classify_prune_bucket():
    assert seer_status.classify_prune_bucket("pending") is None
    assert seer_status.classify_prune_bucket("processing") is None
    assert seer_status.classify_prune_bucket("declined") == "declined"
    assert seer_status.classify_prune_bucket("available") == "completed"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2024-01-02T10:00:00.000Z", 2024),
        ("2024-01-02 10:00:00", 2024),
        ("", None),
        (None, None),
    ],
)
def test_parse_seer_timestamp(value, expected):
    parsed = seer_status.parse_seer_timestamp(value)
    if expected is None:
        assert parsed is None
    else:
        assert parsed.year == expected
