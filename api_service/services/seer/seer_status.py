"""Shared Seer request status constants and classification helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

PENDING_REQUEST_STATUSES = {1, "1", "pending", "PENDING"}
DECLINED_REQUEST_STATUSES = {3, "3", "declined", "DECLINED"}
APPROVED_REQUEST_STATUSES = {2, "2", "approved", "APPROVED"}
FAILED_REQUEST_STATUSES = {4, "4", "failed", "FAILED"}
COMPLETED_REQUEST_STATUSES = {5, "5", "completed", "COMPLETED"}

AVAILABLE_MEDIA_STATUSES = {5, "5", "available", "AVAILABLE"}
PARTIAL_MEDIA_STATUSES = {4, "4", "partially_available", "PARTIALLY_AVAILABLE"}
PROCESSING_MEDIA_STATUSES = {3, "3", "processing", "PROCESSING"}
DELETED_MEDIA_STATUSES = {6, "6", "deleted", "DELETED"}
UNAVAILABLE_MEDIA_STATUSES = {
    1, "1", "unknown", "UNKNOWN",
    2, "2", "pending", "PENDING",
    3, "3", "processing", "PROCESSING",
    4, "4", "partially_available", "PARTIALLY_AVAILABLE",
}


def is_pending_status(status: Any) -> bool:
    """Return True when a Seer request still awaits approve/deny."""
    return status in PENDING_REQUEST_STATUSES


def derive_seer_status(request_status: Any, media_status: Any) -> str:
    """Map Seer request + media status to a SuggestArr status label."""
    if is_pending_status(request_status):
        return "pending"
    if request_status in FAILED_REQUEST_STATUSES:
        return "failed"
    if request_status in DECLINED_REQUEST_STATUSES:
        return "declined"
    if request_status in COMPLETED_REQUEST_STATUSES:
        return "completed"
    if media_status in DELETED_MEDIA_STATUSES:
        return "deleted"
    if media_status in AVAILABLE_MEDIA_STATUSES:
        return "available"
    if media_status in PARTIAL_MEDIA_STATUSES:
        return "partially_available"
    if media_status in PROCESSING_MEDIA_STATUSES:
        return "processing"
    if request_status in APPROVED_REQUEST_STATUSES:
        if media_status in UNAVAILABLE_MEDIA_STATUSES or media_status is None:
            return "unavailable"
        return "approved"
    return "not_found"


def matches_seer_status_filter(seer_status: Optional[str], filter_value: Optional[str]) -> bool:
    """Return True when *seer_status* matches a Requests-page Seer filter."""
    if not filter_value or filter_value == "all":
        return True
    status = seer_status or "not_found"
    if filter_value == "unavailable":
        return status in {"pending", "approved", "processing", "partially_available", "unavailable"}
    if filter_value == "processing":
        return status in {"processing", "partially_available", "approved", "unavailable"}
    return status == filter_value


def classify_prune_bucket(seer_status: str) -> Optional[str]:
    """Return the prune retention bucket for a status, or None when never pruned."""
    if seer_status in {"declined", "failed", "completed", "available", "deleted"}:
        if seer_status == "available":
            return "completed"
        return seer_status
    return None


def parse_seer_timestamp(value: Any) -> Optional[datetime]:
    """Parse a Seer ISO timestamp into a naive UTC datetime."""
    if not value:
        return None
    try:
        text = str(value).strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is not None:
            return parsed.replace(tzinfo=None)
        return parsed
    except (TypeError, ValueError):
        return None
