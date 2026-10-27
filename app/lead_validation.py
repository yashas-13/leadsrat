"""Domain validation shared by the API and unit tests."""
from datetime import datetime, timezone


def validate_follow_up_timestamp(
    activity_type: str,
    next_follow_up_at: datetime | None,
    *,
    now: datetime | None = None,
) -> None:
    """Require future, timezone-aware timestamps for explicit follow-up activities.

    Other activity types retain their existing timestamp semantics.
    """
    if activity_type != "follow_up":
        return
    if next_follow_up_at is None:
        raise ValueError("A next follow-up date and time is required")
    if next_follow_up_at.tzinfo is None or next_follow_up_at.utcoffset() is None:
        raise ValueError("Next follow-up must include a timezone")
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None or reference.utcoffset() is None:
        raise ValueError("Comparison time must include a timezone")
    if next_follow_up_at <= reference:
        raise ValueError("Next follow-up must be in the future")
