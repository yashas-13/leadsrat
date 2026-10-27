"""Reporting date-window and export-safety helpers."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

REPORT_TIME_ZONE = ZoneInfo("Asia/Kolkata")


def report_window(
    start_date: date | None = None,
    end_date: date | None = None,
    *,
    today: date | None = None,
) -> tuple[datetime, datetime, date, date]:
    """Return [start, end-exclusive) UTC bounds for Asia/Kolkata calendar dates.

    If both dates are omitted, default to the last 30 calendar days ending today.
    Partial ranges, reversed dates, and ranges longer than 366 inclusive days are
    rejected so accidental broad exports cannot cause unbounded queries.
    """
    local_today = today or datetime.now(REPORT_TIME_ZONE).date()
    if start_date is None and end_date is None:
        end_date = local_today
        start_date = end_date - timedelta(days=29)
    elif start_date is None or end_date is None:
        raise ValueError("Provide both start_date and end_date")
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")
    if (end_date - start_date).days > 365:
        raise ValueError("Date range cannot exceed 366 calendar days")
    start_at = datetime.combine(start_date, time.min, tzinfo=REPORT_TIME_ZONE).astimezone(timezone.utc)
    end_exclusive = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=REPORT_TIME_ZONE).astimezone(timezone.utc)
    return start_at, end_exclusive, start_date, end_date


def safe_csv_cell(value: object) -> str:
    """Escape spreadsheet formula prefixes before placing untrusted text in CSV."""
    text = "" if value is None else str(value)
    prefix = text.lstrip(" \t\r\n")
    if prefix and prefix[0] in ("=", "+", "-", "@"):
        return "'" + text
    return text
