#!/usr/bin/env python3
"""
Temporary one-off backfill for multi-source metadata ratings.

Fetches IMDB / Rotten Tomatoes / Metacritic (via OMDb) and Trakt community
ratings for existing metadata rows and persists them through the same
enrichment path used at request-save time.

Usage (from api_service/, with app config/env available):

    python backfill_ratings.py
    python backfill_ratings.py --limit 50 --delay 0.5
    python backfill_ratings.py --dry-run
    python backfill_ratings.py --force
    python backfill_ratings.py --only rt_user

On the homelab container (example):

    cd /opt/suggestarr/tmdb-auto/api_service
    python backfill_ratings.py --only rt_user --delay 0.35
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from api_service.config.config import load_env_vars
from api_service.config.logger_manager import LoggerManager
from api_service.db.database_manager import DatabaseManager
from api_service.services.omdb.omdb_client import OmdbClient
from api_service.services.ratings.enrichment import (
    build_enrichment_clients,
    clear_run_ratings_cache,
    enrich_media_ratings,
)

logger = LoggerManager.get_logger("BackfillRatings")


def _placeholder(db: DatabaseManager, query: str) -> str:
    if db.db_type in ("mysql", "postgres"):
        return query.replace("?", "%s")
    return query


def fetch_candidates(
    db: DatabaseManager,
    *,
    missing_only: bool,
    force: bool,
    limit: int | None,
    only: str | None,
) -> list[dict]:
    """Return metadata rows that should be enriched."""
    clauses = ["media_id IS NOT NULL", "media_type IS NOT NULL"]
    if only == "rt_user":
        clauses.append("rt_user_rating IS NULL")
    elif missing_only and not force:
        clauses.append("ratings_updated_at IS NULL")

    limit_sql = ""
    params: list = []
    if limit is not None:
        limit_sql = " LIMIT ?" if db.db_type == "sqlite" else " LIMIT %s"
        params.append(limit)

    query = f"""
        SELECT media_id, media_type, title, rating, imdb_id
        FROM metadata
        WHERE {' AND '.join(clauses)}
        ORDER BY media_id
        {limit_sql}
    """
    query = _placeholder(db, query)

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

    return [
        {
            "id": row[0],
            "media_type": row[1],
            "title": row[2],
            "rating": row[3],
            "imdb_id": row[4],
        }
        for row in rows
    ]


async def _close_clients(tmdb_client, trakt_client, omdb_client=None) -> None:
    if omdb_client is not None:
        await omdb_client.close()
    if tmdb_client is not None:
        if getattr(tmdb_client, "omdb_client", None) is not None:
            await tmdb_client.omdb_client.close()
        await tmdb_client.close()
    if trakt_client is not None:
        await trakt_client.close()


async def _resolve_imdb_id(item: dict, tmdb_client) -> str | None:
    imdb_id = item.get("imdb_id")
    if imdb_id:
        return imdb_id
    if tmdb_client is None:
        return None
    details = await tmdb_client._get_item_details(int(item["id"]), item["media_type"])
    return (details or {}).get("imdb_id")


async def run_rt_user_backfill(
    db: DatabaseManager,
    candidates: list[dict],
    *,
    delay: float,
) -> tuple[int, int, int]:
    """Backfill only Rotten Tomatoes audience scores via OMDb."""
    env = load_env_vars()
    omdb_key = (env.get("OMDB_API_KEY") or "").strip()
    if not omdb_key:
        print("OMDB_API_KEY is required for RT audience backfill.")
        return 0, 0, 1

    tmdb_client, _ = build_enrichment_clients()
    omdb_client = OmdbClient(omdb_key)
    enriched = 0
    skipped = 0
    failed = 0

    try:
        for index, item in enumerate(candidates, start=1):
            media_type = item["media_type"]
            media_id = str(item["id"])
            title = item.get("title") or media_id
            try:
                imdb_id = await _resolve_imdb_id(item, tmdb_client)
                if not imdb_id:
                    skipped += 1
                    print(f"[{index}/{len(candidates)}] no imdb_id {media_type}:{media_id} {title}")
                    continue

                omdb_data = await omdb_client.get_rating(imdb_id)
                rt_user_rating = (omdb_data or {}).get("rt_user_rating")
                if rt_user_rating is None:
                    skipped += 1
                    print(f"[{index}/{len(candidates)}] no rt_user {media_type}:{media_id} {title}")
                else:
                    db.update_metadata_rt_user_rating(media_id, media_type, rt_user_rating)
                    enriched += 1
                    print(
                        f"[{index}/{len(candidates)}] rt_user {media_type}:{media_id} "
                        f"{title} -> {rt_user_rating}%"
                    )
            except Exception as exc:
                failed += 1
                logger.warning(
                    "RT user backfill failed for %s %s: %s",
                    media_type,
                    media_id,
                    exc,
                )
                print(f"[{index}/{len(candidates)}] FAILED {media_type}:{media_id} {title}: {exc}")

            if delay > 0 and index < len(candidates):
                await asyncio.sleep(delay)
    finally:
        await _close_clients(tmdb_client, None, omdb_client)

    return enriched, skipped, failed


async def run_backfill(args: argparse.Namespace) -> int:
    db = DatabaseManager()
    candidates = fetch_candidates(
        db,
        missing_only=args.missing_only,
        force=args.force,
        limit=args.limit,
        only=args.only,
    )

    print(f"Found {len(candidates)} metadata row(s) to process.")
    if not candidates:
        return 0

    if args.dry_run:
        for item in candidates[:20]:
            print(f"  - {item['media_type']}:{item['id']} {item.get('title') or ''}")
        if len(candidates) > 20:
            print(f"  ... and {len(candidates) - 20} more")
        return 0

    if args.only == "rt_user":
        enriched, skipped, failed = await run_rt_user_backfill(
            db, candidates, delay=args.delay
        )
        print()
        print(f"Done. enriched={enriched} skipped={skipped} failed={failed}")
        return 0 if failed == 0 else 1

    tmdb_client, trakt_client = build_enrichment_clients()
    if tmdb_client is None:
        print("TMDB_API_KEY is required for backfill.")
        return 1

    clear_run_ratings_cache()
    enriched = 0
    skipped = 0
    failed = 0

    try:
        for index, item in enumerate(candidates, start=1):
            media_type = item["media_type"]
            title = item.get("title") or item["id"]
            try:
                before = db.get_metadata_ratings(str(item["id"]), media_type) or {}
                media = dict(item)
                await enrich_media_ratings(
                    media,
                    media_type,
                    tmdb_client=tmdb_client,
                    db_manager=db,
                    trakt_client=trakt_client,
                    force_refresh=args.force,
                )
                after = db.get_metadata_ratings(str(item["id"]), media_type) or {}
                got_rating = any(
                    after.get(key) is not None
                    for key in (
                        "imdb_rating",
                        "rt_rating",
                        "rt_user_rating",
                        "metacritic_rating",
                        "trakt_rating",
                    )
                )
                if got_rating and after.get("ratings_updated_at") != before.get("ratings_updated_at"):
                    enriched += 1
                    print(
                        f"[{index}/{len(candidates)}] enriched {media_type}:{item['id']} "
                        f"{title} -> imdb={after.get('imdb_rating')} rt={after.get('rt_rating')} "
                        f"rt_user={after.get('rt_user_rating')} mc={after.get('metacritic_rating')} "
                        f"trakt={after.get('trakt_rating')}"
                    )
                else:
                    skipped += 1
                    print(f"[{index}/{len(candidates)}] no ratings {media_type}:{item['id']} {title}")
            except Exception as exc:
                failed += 1
                logger.warning(
                    "Backfill failed for %s %s: %s",
                    media_type,
                    item["id"],
                    exc,
                )
                print(f"[{index}/{len(candidates)}] FAILED {media_type}:{item['id']} {title}: {exc}")

            if args.delay > 0 and index < len(candidates):
                await asyncio.sleep(args.delay)
    finally:
        await _close_clients(tmdb_client, trakt_client)

    print()
    print(f"Done. enriched={enriched} skipped={skipped} failed={failed}")
    return 0 if failed == 0 else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill multi-source ratings on metadata rows.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max rows to process (default: all matching rows).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.35,
        help="Seconds to wait between API calls (default: 0.35).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List candidate rows without calling external APIs.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Refresh even when ratings_updated_at is already set.",
    )
    parser.add_argument(
        "--only",
        choices=["rt_user"],
        default=None,
        help="Backfill only a single rating field.",
    )
    parser.add_argument(
        "--all",
        dest="missing_only",
        action="store_false",
        help="Include rows that already have ratings_updated_at (without --force, still skips fresh TTL rows in enrich).",
    )
    parser.set_defaults(missing_only=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return asyncio.run(run_backfill(args))


if __name__ == "__main__":
    sys.exit(main())
