from datetime import date, datetime, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.reporting import report_window, safe_csv_cell


def test_report_window_interprets_calendar_days_as_bengaluru_local_time():
    start_at, end_exclusive, start_date, end_date = report_window(
        date(2026, 10, 27), date(2026, 10, 27)
    )
    assert start_at == datetime(2026, 10, 26, 18, 30, tzinfo=timezone.utc)
    assert end_exclusive == datetime(2026, 10, 27, 18, 30, tzinfo=timezone.utc)
    assert start_date == date(2026, 10, 27)
    assert end_date == date(2026, 10, 27)


def test_report_window_defaults_to_last_30_calendar_days():
    _, _, start_date, end_date = report_window(today=date(2026, 10, 27))
    assert start_date == date(2026, 9, 28)
    assert end_date == date(2026, 10, 27)


@pytest.mark.parametrize(
    "start,end",
    [
        (date(2026, 10, 28), date(2026, 10, 27)),
        (date(2025, 1, 1), date(2026, 1, 2)),
        (date(2026, 10, 1), None),
        (None, date(2026, 10, 27)),
    ],
)
def test_report_window_rejects_reversed_oversized_or_partial_ranges(start, end):
    with pytest.raises(ValueError):
        report_window(start, end, today=date(2026, 10, 27))


@pytest.mark.parametrize("value", ["=1+1", "+cmd", "-2+3", "@SUM(A1:A2)", "\t=1+1", " =1+1"])
def test_csv_export_neutralizes_spreadsheet_formula_prefixes(value):
    assert safe_csv_cell(value).startswith("'")
    assert safe_csv_cell(value)[1:] == value


def test_csv_export_preserves_safe_values_and_blank_cells():
    assert safe_csv_cell("Whitefield") == "Whitefield"
    assert safe_csv_cell(0) == "0"
    assert safe_csv_cell(None) == ""
