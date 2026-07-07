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
