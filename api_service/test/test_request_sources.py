"""Tests for request source tag helpers."""
from unittest.mock import patch

from api_service.db import database_manager as dm_mod
from api_service.db.database_manager import DatabaseManager
from api_service.services.request_sources import (
    DISCOVER_SOURCE,
    TRAKT_RECOMMENDATIONS_SOURCE,
    is_tmdb_metadata_source_id,
    request_source_title_sql,
)


def test_trakt_source_is_not_metadata_id():
    assert is_tmdb_metadata_source_id(TRAKT_RECOMMENDATIONS_SOURCE) is False
    assert is_tmdb_metadata_source_id(DISCOVER_SOURCE) is False
    assert is_tmdb_metadata_source_id("27205") is True
    assert is_tmdb_metadata_source_id("ai_search") is False


def test_request_source_title_sql_includes_trakt_label():
    sql = request_source_title_sql("r")
    assert "trakt_recommendations" in sql
    assert "Trakt Recommendations" in sql
    assert "discover" in sql
    assert "Discover" in sql


def test_grouped_requests_labels_synthetic_sources(tmp_path):
    db_file = str(tmp_path / "requests.db")
    with (
        patch.object(dm_mod, "DB_PATH", db_file),
        patch("api_service.db.database_manager.load_env_vars", return_value={"DB_TYPE": "sqlite"}),
    ):
        DatabaseManager._instance = None
        db = DatabaseManager()
        db.save_metadata({"id": "101", "title": "Discover Request"}, "movie")
        db.save_metadata({"id": "202", "title": "Trakt Request"}, "tv")
        db.save_request("movie", "101", DISCOVER_SOURCE)
        db.save_request("tv", "202", TRAKT_RECOMMENDATIONS_SOURCE)

        result = db.get_all_requests_grouped_by_source(page=1, per_page=10)

    DatabaseManager._instance = None

    sources = {item["source_id"]: item for item in result["data"]}
    assert result["total_sources"] == 2
    assert sources[DISCOVER_SOURCE]["source_title"] == "Discover"
    assert sources[TRAKT_RECOMMENDATIONS_SOURCE]["source_title"] == "Trakt Recommendations"


def test_save_metadata_updates_missing_image_paths(tmp_path):
    db_file = str(tmp_path / "requests.db")
    with (
        patch.object(dm_mod, "DB_PATH", db_file),
        patch("api_service.db.database_manager.load_env_vars", return_value={"DB_TYPE": "sqlite"}),
    ):
        DatabaseManager._instance = None
        db = DatabaseManager()
        db.save_metadata({"id": "34524", "title": "Teen Wolf"}, "tv")
        db.save_request("tv", "34524", TRAKT_RECOMMENDATIONS_SOURCE)

        db.save_metadata({
            "id": "34524",
            "title": "Teen Wolf",
            "poster_path": "/teen-wolf.jpg",
            "backdrop_path": "/teen-wolf-bg.jpg",
        }, "tv")

        result = db.get_all_requests_grouped_by_source(page=1, per_page=10)

    DatabaseManager._instance = None

    request = result["data"][0]["requests"][0]
    assert request["poster_path"] == "https://image.tmdb.org/t/p/w500/teen-wolf.jpg"
    assert request["backdrop_path"] == "https://image.tmdb.org/t/p/w1280/teen-wolf-bg.jpg"
