"""Tests for paginated automation request list queries."""
from unittest.mock import patch

from api_service.db import database_manager as dm_mod
from api_service.db.database_manager import DatabaseManager
from api_service.services.request_sources import DISCOVER_SOURCE


def _sqlite_db(tmp_path):
    db_file = str(tmp_path / "requests.db")
    return (
        patch.object(dm_mod, "DB_PATH", db_file),
        patch("api_service.db.database_manager.load_env_vars", return_value={"DB_TYPE": "sqlite"}),
    )


def _seed_many_requests(db, count: int) -> None:
    db.save_metadata({"id": "100", "title": "Seed Movie"}, "movie")
    for index in range(count):
        media_id = str(10_000 + index)
        db.save_metadata({"id": media_id, "title": f"Request {index}"}, "movie")
        db.save_request("movie", media_id, "100")


def test_grouped_requests_paginates_sources_without_loading_all_rows(tmp_path):
    patches = _sqlite_db(tmp_path)
    with patches[0], patches[1]:
        DatabaseManager._instance = None
        db = DatabaseManager()
        _seed_many_requests(db, 120)

        page_one = db.get_all_requests_grouped_by_source(page=1, per_page=1, sort_by="date-desc")
        page_two = db.get_all_requests_grouped_by_source(page=2, per_page=1, sort_by="date-desc")

    DatabaseManager._instance = None

    assert page_one["total_requests"] == 120
    assert page_one["total_sources"] == 1
    assert len(page_one["data"]) == 1
    assert len(page_one["data"][0]["requests"]) <= 50
    assert page_one["data"][0]["has_more_requests"] is True
    assert page_two["data"] == []


def test_flat_requests_use_sql_limit_and_offset(tmp_path):
    patches = _sqlite_db(tmp_path)
    with patches[0], patches[1]:
        DatabaseManager._instance = None
        db = DatabaseManager()
        _seed_many_requests(db, 30)

        page_one = db.get_all_requests_flat(page=1, per_page=10, sort_by="date-desc")
        page_two = db.get_all_requests_flat(page=2, per_page=10, sort_by="date-desc")

    DatabaseManager._instance = None

    assert page_one["total"] == 30
    assert len(page_one["data"]) == 10
    assert len(page_two["data"]) == 10
    assert page_one["data"][0]["request_id"] != page_two["data"][0]["request_id"]


def test_request_count_matches_search_across_all_pages(tmp_path):
    patches = _sqlite_db(tmp_path)
    with patches[0], patches[1]:
        DatabaseManager._instance = None
        db = DatabaseManager()
        for media_id, title in (("1", "The Matrix"), ("2", "Matrix Reloaded"), ("3", "Alien")):
            db.save_metadata({"id": media_id, "title": title}, "movie")
            db.save_request("movie", media_id, DISCOVER_SOURCE)

        count = db.count_requests(search="matrix")

    DatabaseManager._instance = None

    assert count == 2


def test_flat_requests_sort_oldest_first(tmp_path):
    patches = _sqlite_db(tmp_path)
    with patches[0], patches[1]:
        DatabaseManager._instance = None
        db = DatabaseManager()
        db.save_metadata({"id": "older", "title": "Older"}, "movie")
        db.save_metadata({"id": "newer", "title": "Newer"}, "movie")
        db.save_request("movie", "older", DISCOVER_SOURCE, requested_at="2020-01-01T00:00:00")
        db.save_request("movie", "newer", DISCOVER_SOURCE, requested_at="2024-01-01T00:00:00")

        result = db.get_all_requests_flat(page=1, per_page=10, sort_by="date-asc")

    DatabaseManager._instance = None

    assert result["data"][0]["request_id"] == "older"
    assert result["data"][1]["request_id"] == "newer"


def test_flat_requests_filter_by_stored_seer_status(tmp_path):
    patches = _sqlite_db(tmp_path)
    with patches[0], patches[1]:
        DatabaseManager._instance = None
        db = DatabaseManager()
        db.save_metadata({"id": "pending-id", "title": "Pending"}, "movie")
        db.save_metadata({"id": "declined-id", "title": "Declined"}, "movie")
        db.save_request("movie", "pending-id", DISCOVER_SOURCE)
        db.save_request("movie", "declined-id", DISCOVER_SOURCE)
        db.update_request_seer_state("pending-id", "movie", seer_status="pending")
        db.update_request_seer_state("declined-id", "movie", seer_status="declined")

        result = db.get_all_requests_flat(page=1, per_page=10, seer_status_filter="pending")

    DatabaseManager._instance = None

    assert result["total"] == 1
    assert result["data"][0]["request_id"] == "pending-id"
    assert result["data"][0]["seer_status"] == "pending"


def test_grouped_requests_filter_by_seer_status_bucket(tmp_path):
    patches = _sqlite_db(tmp_path)
    with patches[0], patches[1]:
        DatabaseManager._instance = None
        db = DatabaseManager()
        db.save_metadata({"id": "source", "title": "Source"}, "movie")
        db.save_metadata({"id": "approved-id", "title": "Approved"}, "movie")
        db.save_metadata({"id": "available-id", "title": "Available"}, "movie")
        db.save_request("movie", "approved-id", "source")
        db.save_request("movie", "available-id", "source")
        db.update_request_seer_state("approved-id", "movie", seer_status="approved")
        db.update_request_seer_state("available-id", "movie", seer_status="available")

        result = db.get_all_requests_grouped_by_source(
            page=1,
            per_page=10,
            seer_status_filter="unavailable",
        )

    DatabaseManager._instance = None

    assert result["total_requests"] == 1
    assert result["data"][0]["requests"][0]["request_id"] == "approved-id"
    assert result["data"][0]["requests"][0]["seer_status"] == "approved"


def test_get_requests_for_source_paginates(tmp_path):
    patches = _sqlite_db(tmp_path)
    with patches[0], patches[1]:
        DatabaseManager._instance = None
        db = DatabaseManager()
        _seed_many_requests(db, 75)

        page_one = db.get_requests_for_source("100", page=1, per_page=20, sort_by="date-desc")
        page_two = db.get_requests_for_source("100", page=2, per_page=20, sort_by="date-desc")

    DatabaseManager._instance = None

    assert page_one["total_requests"] == 75
    assert len(page_one["data"]["requests"]) == 20
    assert len(page_two["data"]["requests"]) == 20
    assert page_one["data"]["requests"][0]["request_id"] != page_two["data"]["requests"][0]["request_id"]


def test_archive_request_excludes_from_active_checks_and_list(tmp_path):
    patches = _sqlite_db(tmp_path)
    with patches[0], patches[1]:
        DatabaseManager._instance = None
        db = DatabaseManager()
        db.save_metadata({"id": "archived-id", "title": "Archived Movie"}, "movie")
        db.save_request("movie", "archived-id", DISCOVER_SOURCE)

        assert db.check_request_exists("movie", "archived-id") is True
        archived_count = db.archive_request_row("archived-id", "movie", reason="grace_cleanup")
        assert archived_count == 1
        assert db.check_request_exists("movie", "archived-id") is False

        active = db.get_all_requests_flat(page=1, per_page=10)
        archived = db.get_archived_requests_flat(page=1, per_page=10)

    DatabaseManager._instance = None

    assert active["total"] == 0
    assert archived["total"] == 1
    assert archived["data"][0]["archive_reason"] == "grace_cleanup"


def test_save_request_reactivates_archived_row(tmp_path):
    patches = _sqlite_db(tmp_path)
    with patches[0], patches[1]:
        DatabaseManager._instance = None
        db = DatabaseManager()
        db.save_metadata({"id": "reactivate-id", "title": "Reactivate Movie"}, "movie")
        db.save_request("movie", "reactivate-id", DISCOVER_SOURCE, rationale="first")
        db.archive_request_row("reactivate-id", "movie", reason="grace_cleanup")
        assert db.check_request_exists("movie", "reactivate-id") is False

        db.save_request("movie", "reactivate-id", DISCOVER_SOURCE, rationale="second")
        assert db.check_request_exists("movie", "reactivate-id") is True

        active = db.get_all_requests_flat(page=1, per_page=10)
        archived = db.get_archived_requests_flat(page=1, per_page=10)

    DatabaseManager._instance = None

    assert active["total"] == 1
    assert archived["total"] == 0
    assert active["data"][0]["rationale"] == "second"


def test_get_requests_stats_counts_active_and_archived_separately(tmp_path):
    patches = _sqlite_db(tmp_path)
    with patches[0], patches[1]:
        DatabaseManager._instance = None
        db = DatabaseManager()
        db.save_metadata({"id": "active-id", "title": "Active"}, "movie")
        db.save_metadata({"id": "old-id", "title": "Old"}, "movie")
        db.save_request("movie", "active-id", DISCOVER_SOURCE)
        db.save_request("movie", "old-id", DISCOVER_SOURCE)
        db.archive_request_row("old-id", "movie")

        stats = db.get_requests_stats()

    DatabaseManager._instance = None

    assert stats["total"] == 1
    assert stats["archived_count"] == 1
