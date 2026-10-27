from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.team_workflows import build_balanced_assignment_plan


def test_balance_plan_spreads_leads_to_the_lightest_current_agent():
    plan = build_balanced_assignment_plan(
        ["l1", "l2", "l3", "l4"],
        agent_loads={"a": 3, "b": 1, "c": 1},
        agent_names={"a": "Amy", "b": "Ben", "c": "Cara"},
    )
    assert plan == [
        {"lead_id": "l1", "employee_id": "b"},
        {"lead_id": "l2", "employee_id": "c"},
        {"lead_id": "l3", "employee_id": "b"},
        {"lead_id": "l4", "employee_id": "c"},
    ]


def test_balance_plan_tie_breaks_deterministically_by_agent_name():
    assert build_balanced_assignment_plan(
        ["l1", "l2"],
        agent_loads={"z": 2, "b": 2, "a": 2},
        agent_names={"z": "Zed", "b": "Bea", "a": "Ari"},
    ) == [
        {"lead_id": "l1", "employee_id": "a"},
        {"lead_id": "l2", "employee_id": "b"},
    ]


def test_balance_plan_rejects_no_agents_empty_batch_or_duplicates():
    with pytest.raises(ValueError):
        build_balanced_assignment_plan(["l1"], {}, {})
    with pytest.raises(ValueError):
        build_balanced_assignment_plan([], {"a": 1}, {"a": "Amy"})
    with pytest.raises(ValueError):
        build_balanced_assignment_plan(["l1", "l1"], {"a": 1}, {"a": "Amy"})
