from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.lead_validation import validate_follow_up_timestamp


def test_follow_up_requires_a_future_timezone_aware_timestamp():
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    assert validate_follow_up_timestamp("follow_up", now + timedelta(minutes=1), now=now) is None


@pytest.mark.parametrize(
    "timestamp",
    [
        None,
        datetime(2026, 10, 27, 11, 59, tzinfo=timezone.utc),
        datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 27, 13, 0),
    ],
)
def test_follow_up_rejects_missing_past_equal_or_naive_timestamps(timestamp):
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        validate_follow_up_timestamp("follow_up", timestamp, now=now)


def test_non_follow_up_activities_keep_existing_timestamp_contract():
    now = datetime(2026, 10, 27, 11, 59, tzinfo=timezone.utc)
    assert validate_follow_up_timestamp("note", now, now=datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)) is None
