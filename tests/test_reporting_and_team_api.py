from datetime import datetime, timezone, timedelta
import importlib
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def crm(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'crm.db'}")
    monkeypatch.setenv("LEADSRAT_API_KEY", "test-api-key-for-crm-integration-tests-123456")
    monkeypatch.setenv("LEADSRAT_ADMIN_PASSWORD", "test-admin-password-is-long-and-only-for-tests")
    monkeypatch.setenv("LEADSRAT_ADMIN_EMAIL", "admin1@example.test")
    sys.modules.pop("app.main", None)
    module = importlib.import_module("app.main")
    module.Base.metadata.create_all(bind=module.engine)

    now = datetime(2026, 10, 26, 23, 0, tzinfo=timezone.utc)
    future_follow_up = datetime.now(timezone.utc) + timedelta(hours=2)
    org1 = module.Organization(id="org-one", name="One Realty", slug="one-realty")
    org2 = module.Organization(id="org-two", name="Two Realty", slug="two-realty")
    admin = module.Employee(id="admin-one", organization_id=org1.id, name="Admin One", email="admin1@example.test", password_hash=module._hash_password("integration-only-password"), role="admin", active=True)
    agent_a = module.Employee(id="agent-a", organization_id=org1.id, name="Amy Agent", email="amy@example.test", password_hash=module._hash_password("integration-only-password"), role="agent", active=True)
    agent_b = module.Employee(id="agent-b", organization_id=org1.id, name="Ben Agent", email="ben@example.test", password_hash=module._hash_password("integration-only-password"), role="agent", active=True)
    field_user = module.Employee(id="field-user", organization_id=org1.id, name="Field User", email="field@example.test", password_hash=module._hash_password("integration-only-password"), role="readonly", active=True)
    other_admin = module.Employee(id="admin-two", organization_id=org2.id, name="Admin Two", email="admin2@example.test", password_hash=module._hash_password("integration-only-password"), role="admin", active=True)
    leads = [
        module.Lead(id="lead-a", organization_id=org1.id, assigned_to=agent_a.id, name="=1+1", phone_e164="+919900000001", email="formula@example.test", source="integration", status="contacted", locality="Whitefield", property_type="apartment", budget_min_paise=150000000, budget_max_paise=250000000, created_at=now, updated_at=now, next_follow_up_at=future_follow_up),
        module.Lead(id="lead-b", organization_id=org1.id, assigned_to=agent_b.id, name="Won Buyer", phone_e164="+919900000002", email="won@example.test", source="integration", status="won", locality="Sarjapur", property_type="villa", created_at=now + timedelta(minutes=15), updated_at=now, next_follow_up_at=None),
        module.Lead(id="lead-c", organization_id=org1.id, assigned_to=agent_a.id, name="Overdue Buyer", phone_e164=None, email=None, source="integration", status="new", locality="HSR", property_type="plot", created_at=now + timedelta(minutes=30), updated_at=now, next_follow_up_at=now - timedelta(hours=1)),
        module.Lead(id="lead-d", organization_id=org1.id, assigned_to=None, name="Unassigned Buyer", phone_e164=None, email=None, source="integration", status="qualified", locality="Jakkur", property_type="apartment", created_at=now + timedelta(minutes=45), updated_at=now, next_follow_up_at=None),
        module.Lead(id="lead-f", organization_id=org1.id, assigned_to=None, name="Another Unassigned", phone_e164=None, email=None, source="integration", status="new", locality="Yelahanka", property_type="apartment", created_at=now + timedelta(minutes=50), updated_at=now, next_follow_up_at=None),
        module.Lead(id="other-lead", organization_id=org2.id, assigned_to=None, name="Other Tenant Private", phone_e164=None, email="private@other.test", source="integration", status="new", locality="Other", property_type="apartment", created_at=now, updated_at=now, next_follow_up_at=None),
    ]
    activities = [
        module.LeadActivity(id="act-a-contact", organization_id=org1.id, lead_id="lead-a", actor_id=admin.id, activity_type="status_change", message="Status changed from new to contacted", created_at=now + timedelta(minutes=2)),
        module.LeadActivity(id="act-b-contact", organization_id=org1.id, lead_id="lead-b", actor_id=agent_b.id, activity_type="status_change", message="Status changed from new to contacted", created_at=now + timedelta(minutes=17)),
        module.LeadActivity(id="act-b-qualified", organization_id=org1.id, lead_id="lead-b", actor_id=agent_b.id, activity_type="status_change", message="Status changed from contacted to qualified", created_at=now + timedelta(minutes=18)),
        module.LeadActivity(id="act-b-won", organization_id=org1.id, lead_id="lead-b", actor_id=admin.id, activity_type="status_change", message="Status changed from negotiation to won", created_at=now + timedelta(minutes=19)),
        module.LeadActivity(id="act-follow-up", organization_id=org1.id, lead_id="lead-a", actor_id=agent_a.id, activity_type="follow_up", message="Follow-up scheduled", follow_up_at=now + timedelta(hours=2), created_at=now + timedelta(minutes=3)),
    ]
    with module.SessionLocal() as db:
        db.add_all([org1, org2])
        db.add_all([admin, agent_a, agent_b, field_user, other_admin])
        db.add_all(leads)
        db.add_all(activities)
        db.commit()

    admin_cookie = module._session_token(admin, org1, int(time.time()) + 3600)
    field_cookie = module._session_token(field_user, org1, int(time.time()) + 3600)
    client = TestClient(module.app)
    yield {"module": module, "client": client, "admin_cookie": admin_cookie, "field_cookie": field_cookie}
    client.close()
    module.engine.dispose()
    sys.modules.pop("app.main", None)


def _headers(cookie):
    return {"Cookie": f"leadsrat_session={cookie}"}


def test_reports_are_tenant_scoped_role_gated_and_date_ranged(crm):
    client = crm["client"]
    headers = _headers(crm["admin_cookie"])
    response = client.get("/api/v1/reports/summary?start_date=2026-10-27&end_date=2026-10-27", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["date_range"] == {"start_date": "2026-10-27", "end_date": "2026-10-27", "timezone": "Asia/Kolkata"}
    assert body["cohort"]["leads_created"] == 5
    assert body["cohort"]["contacted_leads"] == 2
    assert body["cohort"]["qualified_leads"] == 1
    assert body["cohort"]["won_leads"] == 1
    assert body["follow_up"]["overdue_active_leads_now"] == 1
    assert body["follow_up"]["unscheduled_active_leads_now"] == 2
    assert "Other Tenant Private" not in response.text

    invalid = client.get("/api/v1/reports/summary?start_date=2026-10-28&end_date=2026-10-27", headers=headers)
    assert invalid.status_code == 422
    field_forbidden = client.get("/api/v1/reports/summary?start_date=2026-10-27&end_date=2026-10-27", headers=_headers(crm["field_cookie"]))
    assert field_forbidden.status_code == 403


def test_csv_export_is_tenant_scoped_and_formula_safe(crm):
    response = crm["client"].get(
        "/api/v1/reports/export.csv?start_date=2026-10-27&end_date=2026-10-27",
        headers=_headers(crm["admin_cookie"]),
    )
    assert response.status_code == 200, response.text
    assert "text/csv" in response.headers["content-type"]
    assert "attachment; filename=" in response.headers["content-disposition"]
    contents = response.content.decode("utf-8-sig")
    assert "Other Tenant Private" not in contents
    assert "private@other.test" not in contents
    assert "'=1+1" in contents
    assert "lead_name" in contents


def test_bulk_assignment_is_atomic_and_rejects_cross_tenant_ids(crm):
    module, client = crm["module"], crm["client"]
    headers = _headers(crm["admin_cookie"])
    result = client.post(
        "/api/v1/leads/assignments/bulk",
        headers=headers,
        json={"lead_ids": ["lead-d", "other-lead"], "employee_id": "agent-b"},
    )
    assert result.status_code == 404
    with module.SessionLocal() as db:
        lead = db.get(module.Lead, "lead-d")
        assert lead.assigned_to is None

    good = client.post(
        "/api/v1/leads/assignments/bulk",
        headers=headers,
        json={"lead_ids": ["lead-d"], "employee_id": "agent-b"},
    )
    assert good.status_code == 200, good.text
    assert good.json()["changed_count"] == 1
    with module.SessionLocal() as db:
        lead = db.get(module.Lead, "lead-d")
        assert lead.assigned_to == "agent-b"
        logged = db.scalar(select(module.LeadActivity).where(module.LeadActivity.lead_id == "lead-d"))
        assert logged is not None and "Ben Agent" in logged.message


def test_balance_selected_leads_uses_least_loaded_active_agents(crm):
    module, client = crm["module"], crm["client"]
    response = client.post(
        "/api/v1/leads/assignments/balance",
        headers=_headers(crm["admin_cookie"]),
        json={"lead_ids": ["lead-d", "lead-f"]},
    )
    assert response.status_code == 200, response.text
    assignments = response.json()["assignments"]
    assert assignments == [
        {"lead_id": "lead-d", "employee_id": "agent-b", "employee_name": "Ben Agent"},
        {"lead_id": "lead-f", "employee_id": "agent-b", "employee_name": "Ben Agent"},
    ]
    with module.SessionLocal() as db:
        assert db.get(module.Lead, "lead-d").assigned_to == "agent-b"
        assert db.get(module.Lead, "lead-f").assigned_to == "agent-b"


def test_follow_up_activity_requires_future_time_and_persists_in_organization(crm):
    module, client = crm["module"], crm["client"]
    headers = _headers(crm["admin_cookie"])
    missing = client.post(
        "/api/v1/leads/lead-a/activities",
        headers=headers,
        json={"activity_type": "follow_up", "message": "Missing schedule"},
    )
    assert missing.status_code == 422

    past = client.post(
        "/api/v1/leads/lead-a/activities",
        headers=headers,
        json={
            "activity_type": "follow_up",
            "message": "Past schedule",
            "next_follow_up_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        },
    )
    assert past.status_code == 422

    future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(microsecond=0)
    created = client.post(
        "/api/v1/leads/lead-a/activities",
        headers=headers,
        json={
            "activity_type": "follow_up",
            "message": "Next buyer check-in",
            "next_follow_up_at": future_time.isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    with module.SessionLocal() as db:
        lead = db.get(module.Lead, "lead-a")
        assert lead.next_follow_up_at is not None
        assert lead.next_follow_up_at.replace(tzinfo=timezone.utc) == future_time.replace(microsecond=0)
        activity = db.get(module.LeadActivity, created.json()["id"])
        assert activity.organization_id == "org-one"
        assert activity.lead_id == "lead-a"
