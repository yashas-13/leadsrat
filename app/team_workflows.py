"""Deterministic load-balancing logic for selected CRM leads."""
from collections.abc import Mapping, Sequence


def build_balanced_assignment_plan(
    lead_ids: Sequence[str],
    agent_loads: Mapping[str, int],
    agent_names: Mapping[str, str],
) -> list[dict[str, str]]:
    """Greedily assign each lead to the lightest active agent.

    Existing active-lead workload is the starting weight. Ties are stable by
    case-insensitive display name, then employee ID, making dry-runs testable.
    """
    if not lead_ids:
        raise ValueError("Select at least one lead")
    if len(set(lead_ids)) != len(lead_ids):
        raise ValueError("Lead IDs must be unique")
    agent_ids = list(agent_loads)
    if not agent_ids:
        raise ValueError("No active agents are available for assignment")
    if any(agent_id not in agent_names for agent_id in agent_ids):
        raise ValueError("Every active agent needs a display name")
    loads = {agent_id: max(0, int(agent_loads[agent_id])) for agent_id in agent_ids}
    assignments: list[dict[str, str]] = []
    for lead_id in lead_ids:
        employee_id = min(
            agent_ids,
            key=lambda candidate: (
                loads[candidate],
                agent_names[candidate].casefold(),
                candidate,
            ),
        )
        assignments.append({"lead_id": lead_id, "employee_id": employee_id})
        loads[employee_id] += 1
    return assignments
