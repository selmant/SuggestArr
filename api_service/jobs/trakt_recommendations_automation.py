"""
Trakt Recommendations Automation for executing trakt_recommendations jobs.
Fetches personalized recommendations from Trakt and requests them via Seer.
"""
import traceback
from typing import Any, Dict, List, Optional

from api_service.config.logger_manager import LoggerManager
from api_service.db.database_manager import DatabaseManager
from api_service.db.job_repository import JobRepository
from api_service.jobs.discover_automation import ExecutionResult
from api_service.jobs._trakt_automation_base import TraktJobAutomationBase
from api_service.services.config_service import ConfigService
from api_service.services.request_sources import TRAKT_RECOMMENDATIONS_SOURCE
from api_service.services.trakt.media_user_augmentor import TraktAccountResolver
from api_service.services.trakt.trakt_client import TraktClient, TRAKT_RECOMMENDATIONS_LIMIT_MAX


class TraktRecommendationsAutomation(TraktJobAutomationBase):
    """Automates fetching Trakt personalized recommendations and requesting via Seer."""

    def __init__(self):
        """Initialize with logger only. Use create() for full initialization."""
        super().__init__()
        self.trakt_client: Optional[TraktClient] = None

    @classmethod
    async def create(cls, job_id: int, dry_run: bool = False) -> "TraktRecommendationsAutomation":
        """Create and initialize TraktRecommendationsAutomation for a job.

        Args:
            job_id: ID of the trakt_recommendations job to execute.
            dry_run: If True, skip request-cache sync during initialization.

        Returns:
            Initialized TraktRecommendationsAutomation instance.

        Raises:
            ValueError: If the job is missing or misconfigured.
        """
        instance = cls()
        instance.job_id = job_id
        instance.repository = JobRepository()
        instance.db_manager = DatabaseManager()
        instance.env_vars = ConfigService.get_runtime_config()

        instance.job_data = instance.repository.get_job(job_id)
        if not instance.job_data:
            raise ValueError(f"Job not found: {job_id}")
        if instance.job_data.get("job_type") != "trakt_recommendations":
            raise ValueError(f"Job {job_id} is not a trakt_recommendations job")

        instance.logger.info(
            "Initializing TraktRecommendationsAutomation for job: %s",
            instance.job_data["name"],
        )
        await instance._initialize_components(dry_run=dry_run)
        instance.logger.info("TraktRecommendationsAutomation initialized successfully")
        return instance

    async def _initialize_components(self, dry_run: bool = False) -> None:
        """Initialize Seer, Trakt, and TMDb clients from job configuration."""
        await self._initialize_shared_components(dry_run=dry_run)
        self.trakt_client = self._build_trakt_client()

    def _build_trakt_client(self) -> TraktClient:
        """Resolve the linked Trakt account for the configured media user."""
        user_ids = self.job_data.get("user_ids") or []
        if len(user_ids) != 1:
            raise ValueError("Trakt recommendations job requires exactly one linked media user")

        provider = str(self.env_vars.get("SELECTED_SERVICE") or "").lower()
        external_user_id = str(user_ids[0])
        identity = self.db_manager.get_media_user_identity(provider, external_user_id)
        resolved = TraktAccountResolver(self.db_manager).resolve(identity["id"])
        if not resolved:
            raise ValueError(
                f"Media user {external_user_id} has no connected Trakt account"
            )

        client_id, client_secret = self._get_trakt_app_credentials()
        return TraktClient(
            client_id,
            client_secret,
            access_token=resolved.get("access_token", ""),
            refresh_token=resolved.get("refresh_token", ""),
            expires_at=resolved.get("expires_at"),
            db=self.db_manager,
            link_id=resolved["id"],
            token_source=resolved.get("token_source", "manual_oauth"),
        )

    async def run(self, dry_run: bool = False) -> ExecutionResult:
        """Execute the Trakt recommendations job.

        Args:
            dry_run: When True, simulate without enqueueing requests.

        Returns:
            ExecutionResult with execution details.
        """
        if not self.job_data:
            return ExecutionResult(
                success=False,
                results_count=0,
                requested_count=0,
                error_message="Job not initialized",
            )

        self.logger.info(
            "%sStarting trakt recommendations job: %s",
            "[DRY RUN] " if dry_run else "",
            self.job_data["name"],
        )
        exec_id = None if dry_run else self.repository.log_execution_start(self.job_id)

        try:
            from contextlib import AsyncExitStack

            async with AsyncExitStack() as stack:
                if self.seer_client:
                    await stack.enter_async_context(self.seer_client)
                if self.tmdb_client:
                    await stack.enter_async_context(self.tmdb_client)
                    if self.tmdb_client.omdb_client:
                        await stack.enter_async_context(self.tmdb_client.omdb_client)
                if self.trakt_client:
                    await stack.enter_async_context(self.trakt_client)

                results = await self.fetch_trakt_recommendations()
            results_count = len(results)
            self.logger.info("Fetched %d Trakt recommendations after filtering", results_count)

            requested_count, dry_run_items = await self.filter_and_request(results, dry_run=dry_run)

            if not dry_run:
                self.repository.log_execution_end(
                    exec_id=exec_id,
                    status="completed",
                    results_count=results_count,
                    requested_count=requested_count,
                )

            return ExecutionResult(
                success=True,
                results_count=results_count,
                requested_count=requested_count,
                dry_run_items=dry_run_items,
            )
        except Exception as exc:
            error_msg = str(exc) if str(exc) else type(exc).__name__
            self.logger.error("Job failed: %s", error_msg)
            self.logger.error("Traceback: %s", traceback.format_exc())

            if not dry_run and exec_id is not None:
                self.repository.log_execution_end(
                    exec_id=exec_id,
                    status="failed",
                    results_count=0,
                    requested_count=0,
                    error_message=error_msg,
                )

            return ExecutionResult(
                success=False,
                results_count=0,
                requested_count=0,
                error_message=error_msg,
            )

    async def fetch_trakt_recommendations(self) -> List[Dict[str, Any]]:
        """Fetch and filter Trakt recommendations for the configured media types."""
        job_filters = self.job_data.get("filters", {})
        media_type = self.job_data.get("media_type", "movie")
        max_results = int(self.job_data.get("max_results") or 20)
        fetch_limit = max(max_results * 3, max_results)

        ignore_collected = bool(job_filters.get("ignore_collected", True))
        ignore_watched = bool(job_filters.get("ignore_watched", True))

        media_types = ["movie", "tv"] if media_type == "both" else [media_type]
        if len(media_types) == 1:
            per_type_limit = min(TRAKT_RECOMMENDATIONS_LIMIT_MAX, fetch_limit)
        else:
            # Recommendations do not paginate; request Trakt's max per type.
            per_type_limit = TRAKT_RECOMMENDATIONS_LIMIT_MAX

        raw_items: List[Dict[str, Any]] = []
        trakt_counts: Dict[str, int] = {}
        for item_type in media_types:
            trakt_items = await self.trakt_client.get_recommendations(
                item_type,
                limit=per_type_limit,
                ignore_collected=ignore_collected,
                ignore_watched=ignore_watched,
            )
            trakt_counts[item_type] = len(trakt_items)
            for item in trakt_items:
                raw_items.append({**item, "media_type": item_type})

        filtered: List[Dict[str, Any]] = []
        stats = {
            "missing_tmdb_id": 0,
            "skipped_dedup": 0,
            "failed_quality_filter": 0,
            "kept": 0,
        }
        for item in raw_items:
            item_media_type = item.get("media_type") or media_type
            tmdb_id = item.get("tmdb_id")
            if not tmdb_id:
                stats["missing_tmdb_id"] += 1
                continue
            if await self._should_skip_global_request(item_media_type, tmdb_id):
                stats["skipped_dedup"] += 1
                continue

            enriched = await self._enrich_and_filter_item(item)
            if enriched:
                filtered.append(enriched)
                stats["kept"] += 1
            else:
                stats["failed_quality_filter"] += 1
            if len(filtered) >= max_results:
                break

        self.logger.info(
            "Trakt recommendations fetch stats (target=%d, media_type=%s, "
            "per_type_limit=%d, ignore_collected=%s, ignore_watched=%s): "
            "trakt_returned=%s, raw=%d, missing_tmdb=%d, skipped_dedup=%d, "
            "failed_quality_filter=%d, kept=%d",
            max_results,
            media_type,
            per_type_limit,
            ignore_collected,
            ignore_watched,
            trakt_counts,
            len(raw_items),
            stats["missing_tmdb_id"],
            stats["skipped_dedup"],
            stats["failed_quality_filter"],
            stats["kept"],
        )
        return filtered[:max_results]

    async def filter_and_request(
        self,
        results: List[Dict[str, Any]],
        dry_run: bool = False,
    ):
        """Filter discovered content and request via Seer."""
        requested_count = 0
        dry_run_items: Optional[List[Dict[str, Any]]] = [] if dry_run else None

        for item in results:
            media_type = item.get("media_type") or self.job_data.get("media_type", "movie")
            tmdb_id = item["id"]
            title = item.get("title") or item.get("name") or "Unknown"

            try:
                if await self._should_skip_global_request(media_type, tmdb_id):
                    continue

                if dry_run:
                    dry_run_items.append(self._format_dry_run_item(media_type, item))
                    requested_count += 1
                    continue

                success = await self.seer_client.request_media(
                    media_type,
                    item,
                    source={"id": TRAKT_RECOMMENDATIONS_SOURCE},
                    user=None,
                )
                if success:
                    requested_count += 1
            except Exception as exc:
                self.logger.error("Error processing %s: %s", title, exc)
                continue

        return requested_count, dry_run_items


async def execute_trakt_recommendations_job(job_id: int) -> ExecutionResult:
    """Execute a trakt_recommendations job by ID."""
    logger = LoggerManager.get_logger("TraktRecommendationsJobExecutor")
    logger.info("Starting execution of trakt recommendations job: %s", job_id)

    try:
        automation = await TraktRecommendationsAutomation.create(job_id)
        return await automation.run()
    except Exception as exc:
        logger.error("Failed to execute job %s: %s", job_id, exc)
        logger.error("Traceback: %s", traceback.format_exc())
        return ExecutionResult(
            success=False,
            results_count=0,
            requested_count=0,
            error_message=str(exc),
        )
