from __future__ import annotations

import base64
import csv
import hashlib
import io
import hmac
import json
import os
import re
import secrets
import time
import uuid
from datetime import date, datetime, timezone, timedelta

from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, create_engine, func, select, text, ForeignKey, and_, or_
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.lead_validation import validate_follow_up_timestamp
from app.reporting import report_window, safe_csv_cell
from app.team_workflows import build_balanced_assignment_plan

DATABASE_URL = os.environ.get("DATABASE_URL", "")
API_KEY = os.environ.get("LEADSRAT_API_KEY", "")
ADMIN_PASSWORD = os.environ.get("LEADSRAT_ADMIN_PASSWORD", "")
ADMIN_EMAIL = os.environ.get("LEADSRAT_ADMIN_EMAIL", "admin@parkzone.in").strip().lower()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required")
if len(API_KEY) < 32:
    raise RuntimeError("LEADSRAT_API_KEY must be at least 32 characters")
if len(ADMIN_PASSWORD) < 20:
    raise RuntimeError("LEADSRAT_ADMIN_PASSWORD must be at least 20 characters")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=5)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(24), nullable=False, default="agent")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 310000).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, digest = stored.split("$", 2)
        if scheme != "pbkdf2_sha256": return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 310000).hex()
        return hmac.compare_digest(actual, digest)
    except (ValueError, TypeError):
        return False


class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str | None] = mapped_column(String(36), index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(36), index=True)
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone_e164: Mapped[str | None] = mapped_column(String(20), index=True)
    email: Mapped[str | None] = mapped_column(String(254), index=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="new", index=True)
    locality: Mapped[str | None] = mapped_column(String(120))
    property_type: Mapped[str | None] = mapped_column(String(40))
    budget_min_paise: Mapped[int | None] = mapped_column(BigInteger)
    budget_max_paise: Mapped[int | None] = mapped_column(BigInteger)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class LeadActivity(Base):
    __tablename__ = "lead_activities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    lead_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), index=True)
    activity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    call_outcome: Mapped[str | None] = mapped_column(String(40))
    call_summary: Mapped[str | None] = mapped_column(Text)
    next_step: Mapped[str | None] = mapped_column(Text)
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)


class Property(Base):
    __tablename__ = "properties"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str | None] = mapped_column(String(36), index=True)
    project_name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    developer_name: Mapped[str | None] = mapped_column(String(180))
    locality: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    property_type: Mapped[str] = mapped_column(String(40), nullable=False)
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    area_sqft: Mapped[int | None] = mapped_column(Integer)
    price_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    availability: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown", index=True)
    rera_number: Mapped[str | None] = mapped_column(String(80))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class LeadCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=160)
    phone_e164: str | None = Field(default=None, max_length=20, pattern=r"^\+[1-9][0-9]{7,14}$")
    email: str | None = Field(default=None, max_length=254)
    source: str = Field(default="manual", min_length=1, max_length=80)
    locality: str | None = Field(default=None, max_length=120)
    property_type: str | None = Field(default=None, max_length=40)
    budget_min_paise: int | None = Field(default=None, ge=0)
    budget_max_paise: int | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=4000)
    next_follow_up_at: datetime

    @field_validator("next_follow_up_at")
    @classmethod
    def first_follow_up_must_be_future(cls, value):
        check = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if check <= datetime.now(timezone.utc):
            raise ValueError("next_follow_up_at must be in the future")
        return check

    @field_validator("budget_max_paise")
    @classmethod
    def max_budget_after_min(cls, v, info):
        low = info.data.get("budget_min_paise")
        if v is not None and low is not None and v < low:
            raise ValueError("budget_max_paise must be >= budget_min_paise")
        return v


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    phone_e164: str | None
    email: str | None
    source: str
    status: str
    locality: str | None
    property_type: str | None
    budget_min_paise: int | None
    budget_max_paise: int | None
    notes: str | None
    organization_id: str | None = None
    assigned_to: str | None = None
    last_contact_at: datetime | None = None
    next_follow_up_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PropertyCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    project_name: str = Field(min_length=1, max_length=180)
    developer_name: str | None = Field(default=None, max_length=180)
    locality: str = Field(min_length=1, max_length=120)
    property_type: Literal["apartment", "villa", "plot", "penthouse", "other"]
    bedrooms: int | None = Field(default=None, ge=0, le=20)
    area_sqft: int | None = Field(default=None, gt=0, le=1_000_000)
    price_paise: int = Field(gt=0)
    availability: Literal["available", "reserved", "sold", "unknown"] = "unknown"
    rera_number: str | None = Field(default=None, max_length=80)


class PropertyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_name: str
    developer_name: str | None
    locality: str
    property_type: str
    bedrooms: int | None
    area_sqft: int | None
    price_paise: int
    availability: str
    rera_number: str | None
    verified_at: datetime | None
    created_at: datetime


class StatusUpdate(BaseModel):
    status: Literal["new", "contacted", "qualified", "site_visit", "negotiation", "won", "lost", "nurture"]
    note: str | None = Field(default=None, max_length=2000)
    next_follow_up_at: datetime | None = None


app = FastAPI(title="Leadsrat API", version="0.1.0", description="Bangalore real-estate lead and property CRM API", root_path="/leadsrat")


def get_db():
    with SessionLocal() as db:
        yield db


DB = Annotated[Session, Depends(get_db)]

def _session_token(user: Employee, organization: Organization, expiry: int) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"sub": user.id, "org": organization.id, "role": user.role, "name": user.name, "email": user.email, "exp": expiry}, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(API_KEY.encode(), payload.encode(), "sha256").hexdigest()
    return payload + "." + signature


def _session_actor(token: str | None) -> dict | None:
    if not token: return None
    try:
        payload, signature = token.split(".", 1)
        expected = hmac.new(API_KEY.encode(), payload.encode(), "sha256").hexdigest()
        if not hmac.compare_digest(signature, expected): return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if int(data.get("exp", 0)) < int(time.time()): return None
        return data
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _valid_session(token: str | None) -> bool:
    return _session_actor(token) is not None


def require_api_key(request: Request, db: DB, x_api_key: Annotated[str | None, Header()] = None):
    if x_api_key and hmac.compare_digest(x_api_key, API_KEY):
        request.state.actor = {"role": "service", "org": None, "sub": None}
        return
    actor = _session_actor(request.cookies.get("leadsrat_session"))
    if actor:
        user = db.get(Employee, actor.get("sub"))
        if user and user.active and user.organization_id == actor.get("org"):
            request.state.actor = actor
            now = datetime.now(timezone.utc)
            last_seen_at = user.last_seen_at
            if last_seen_at is not None and last_seen_at.tzinfo is None:
                last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)
            if last_seen_at is None or last_seen_at < now - timedelta(seconds=30):
                user.last_seen_at = now
                db.commit()
            return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")


Auth = Annotated[None, Depends(require_api_key)]

def _actor(request: Request) -> dict:
    actor = getattr(request.state, "actor", None)
    if not actor: raise HTTPException(status_code=401, detail="Authentication required")
    return actor


def _require_role(request: Request, *roles: str) -> dict:
    actor = _actor(request)
    if actor.get("role") not in roles:
        raise HTTPException(status_code=403, detail="Your role does not permit this action")
    return actor


def _scoped(query, model, actor: dict):
    if actor.get("role") == "service": return query
    query = query.where(model.organization_id == actor["org"])
    if model is Lead and actor.get("role") == "agent":
        query = query.where(Lead.assigned_to == actor["sub"])
    return query


@app.get("/admin", include_in_schema=False)
def admin_portal():
    return RedirectResponse(url="/leadsrat/?portal=admin", status_code=303)


@app.get("/employee", include_in_schema=False)
def employee_portal():
    return RedirectResponse(url="/leadsrat/?portal=employee", status_code=303)


@app.post("/api/v1/auth/login")
def login(payload: dict, response: Response, db: DB):
    password = payload.get("password", "")
    email = str(payload.get("email", "")).strip().lower()
    if not isinstance(password, str) or not password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if email:
        user = db.scalar(select(Employee).where(Employee.email == email, Employee.active.is_(True)))
        if not user or not _verify_password(password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")
    else:
        if not hmac.compare_digest(password, ADMIN_PASSWORD):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        user = db.scalar(select(Employee).where(Employee.email == ADMIN_EMAIL, Employee.active.is_(True)))
        if not user:
            raise HTTPException(status_code=401, detail="Admin account is not provisioned")
    portal = str(payload.get("portal", "")).strip().lower()
    if portal == "admin" and user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="This account must use the employee portal")
    if portal == "employee" and user.role not in ("agent", "readonly"):
        raise HTTPException(status_code=403, detail="This account must use the organization admin portal")
    organization = db.get(Organization, user.organization_id)
    if not organization or not user.active:
        raise HTTPException(status_code=401, detail="Account is unavailable")
    user.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    expiry = int(time.time()) + 8 * 60 * 60
    response.set_cookie("leadsrat_session", _session_token(user, organization, expiry), max_age=8 * 60 * 60, httponly=True, secure=True, samesite="strict", path="/leadsrat/")
    return {"authenticated": True, "expires_at": expiry, "user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role}, "organization": {"id": organization.id, "name": organization.name}}


@app.post("/api/v1/auth/logout")
def logout(response: Response):
    response.delete_cookie("leadsrat_session", path="/leadsrat/", secure=True, httponly=True, samesite="strict")
    return {"authenticated": False}


@app.get("/api/v1/auth/session")
def session_status(request: Request, db: DB):
    actor = _session_actor(request.cookies.get("leadsrat_session"))
    if not actor: return {"authenticated": False}
    user = db.get(Employee, actor.get("sub"))
    if not user or not user.active or user.organization_id != actor.get("org"):
        return {"authenticated": False}
    org = db.get(Organization, user.organization_id)
    return {"authenticated": bool(org), "user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role}, "organization": {"id": org.id, "name": org.name} if org else None}


class EmployeeCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=12, max_length=256)
    role: Literal["manager", "agent", "readonly"] = "agent"

    @field_validator("email")
    @classmethod
    def normalize_and_validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid work email address")
        return value


class EmployeeUpdate(BaseModel):
    role: Literal["manager", "agent", "readonly"] | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=12, max_length=256)


class LeadAssignment(BaseModel):
    employee_id: str | None = None


class LeadBatch(BaseModel):
    lead_ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator("lead_ids")
    @classmethod
    def validate_unique_lead_ids(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item or len(item) > 36 for item in cleaned):
            raise ValueError("Lead IDs must be non-empty IDs no longer than 36 characters")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Lead IDs must be unique")
        return cleaned


class BulkLeadAssignment(LeadBatch):
    employee_id: str = Field(min_length=1, max_length=36)


class ActivityCreate(BaseModel):
    activity_type: Literal["call", "whatsapp", "email", "site_visit", "meeting", "note", "status_change", "follow_up"] = "note"
    message: str = Field(default="", max_length=2000)
    call_outcome: Literal["connected", "no_answer", "callback", "interested", "not_interested", "qualified", "site_visit", "won", "lost", "other"] | None = None
    call_summary: str | None = Field(default=None, max_length=5000)
    next_step: str | None = Field(default=None, max_length=2000)
    next_follow_up_at: datetime | None = None
    status: Literal["new", "contacted", "qualified", "site_visit", "negotiation", "won", "lost", "nurture"] | None = None

    @field_validator("call_summary", "next_step", "message")
    @classmethod
    def strip_activity_text(cls, value):
        return value.strip() if value else value


@app.patch("/api/v1/leads/{lead_id}/assign")
def assign_lead(lead_id: str, payload: LeadAssignment, request: Request, db: DB, _auth: Auth):
    actor = _require_role(request, "admin", "manager")
    lead = db.scalar(_scoped(select(Lead).where(Lead.id == lead_id), Lead, actor))
    if not lead: raise HTTPException(status_code=404, detail="Lead not found")
    if payload.employee_id:
        employee = db.scalar(select(Employee).where(Employee.id == payload.employee_id, Employee.organization_id == actor["org"], Employee.active.is_(True), Employee.role == "agent"))
        if not employee: raise HTTPException(status_code=400, detail="Choose an active agent from your organization")
        lead.assigned_to = employee.id
        assignment_message = f"Lead assigned to {employee.name}"
    else:
        lead.assigned_to = None
        assignment_message = "Lead unassigned"
    db.add(LeadActivity(organization_id=lead.organization_id or actor["org"], lead_id=lead.id, actor_id=actor.get("sub"), activity_type="note", message=assignment_message))
    db.commit(); db.refresh(lead)
    return {"id": lead.id, "assigned_to": lead.assigned_to}


def _select_org_leads_for_assignment(db: Session, actor: dict, lead_ids: list[str]) -> list[Lead]:
    rows = db.scalars(
        select(Lead)
        .where(Lead.organization_id == actor["org"], Lead.id.in_(lead_ids))
        .with_for_update()
    ).all()
    by_id = {lead.id: lead for lead in rows}
    if len(by_id) != len(lead_ids):
        raise HTTPException(status_code=404, detail="One or more selected leads were not found in this organization")
    return [by_id[lead_id] for lead_id in lead_ids]


@app.post("/api/v1/leads/assignments/bulk")
def bulk_assign_leads(payload: BulkLeadAssignment, request: Request, db: DB, _auth: Auth):
    actor = _require_role(request, "admin", "manager")
    employee = db.scalar(
        select(Employee).where(
            Employee.id == payload.employee_id,
            Employee.organization_id == actor["org"],
            Employee.active.is_(True),
            Employee.role == "agent",
        )
    )
    if not employee:
        raise HTTPException(status_code=400, detail="Choose an active agent from your organization")
    leads_to_assign = _select_org_leads_for_assignment(db, actor, payload.lead_ids)
    changed = 0
    for lead in leads_to_assign:
        if lead.assigned_to == employee.id:
            continue
        lead.assigned_to = employee.id
        db.add(LeadActivity(
            organization_id=actor["org"],
            lead_id=lead.id,
            actor_id=actor.get("sub"),
            activity_type="note",
            message=f"Lead bulk-assigned to {employee.name}",
        ))
        changed += 1
    db.commit()
    return {
        "selected_count": len(leads_to_assign),
        "changed_count": changed,
        "employee_id": employee.id,
        "employee_name": employee.name,
        "lead_ids": [lead.id for lead in leads_to_assign],
    }


@app.post("/api/v1/leads/assignments/balance")
def balance_lead_assignments(payload: LeadBatch, request: Request, db: DB, _auth: Auth):
    actor = _require_role(request, "admin", "manager")
    leads_to_assign = _select_org_leads_for_assignment(db, actor, payload.lead_ids)
    agents = db.scalars(
        select(Employee)
        .where(
            Employee.organization_id == actor["org"],
            Employee.active.is_(True),
            Employee.role == "agent",
        )
        .order_by(Employee.name.asc(), Employee.id.asc())
    ).all()
    if not agents:
        raise HTTPException(status_code=409, detail="Create or reactivate an agent before balancing lead assignments")
    agent_ids = [agent.id for agent in agents]
    names = {agent.id: agent.name for agent in agents}
    loads = {agent_id: 0 for agent_id in agent_ids}
    workload_rows = db.execute(
        select(Lead.assigned_to, func.count(Lead.id))
        .where(
            Lead.organization_id == actor["org"],
            Lead.assigned_to.in_(agent_ids),
            Lead.status.notin_(["won", "lost"]),
            Lead.id.notin_(payload.lead_ids),
        )
        .group_by(Lead.assigned_to)
    ).all()
    loads.update({employee_id: count for employee_id, count in workload_rows if employee_id})
    try:
        plan = build_balanced_assignment_plan(
            [lead.id for lead in leads_to_assign], loads, names
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    lead_by_id = {lead.id: lead for lead in leads_to_assign}
    changed = 0
    for item in plan:
        lead = lead_by_id[item["lead_id"]]
        employee_id = item["employee_id"]
        if lead.assigned_to != employee_id:
            lead.assigned_to = employee_id
            db.add(LeadActivity(
                organization_id=actor["org"],
                lead_id=lead.id,
                actor_id=actor.get("sub"),
                activity_type="note",
                message=f"Lead assigned by workload balancing to {names[employee_id]}",
            ))
            changed += 1
    db.commit()
    return {
        "selected_count": len(plan),
        "changed_count": changed,
        "assignments": [
            {
                "lead_id": item["lead_id"],
                "employee_id": item["employee_id"],
                "employee_name": names[item["employee_id"]],
            }
            for item in plan
        ],
    }


@app.get("/api/v1/leads/{lead_id}/activities")
def list_lead_activities(lead_id: str, request: Request, db: DB, _auth: Auth, limit: int = Query(default=50, ge=1, le=100)):
    actor = _actor(request)
    lead = db.scalar(_scoped(select(Lead).where(Lead.id == lead_id), Lead, actor))
    if not lead: raise HTTPException(status_code=404, detail="Lead not found")
    org_id = lead.organization_id or actor.get("org")
    rows = db.scalars(select(LeadActivity).where(LeadActivity.lead_id == lead_id, LeadActivity.organization_id == org_id).order_by(LeadActivity.created_at.desc()).limit(limit)).all()
    by_id = {u.id: u.name for u in db.scalars(select(Employee).where(Employee.organization_id == org_id)).all()}
    return [{"id": a.id, "activity_type": a.activity_type, "message": a.message, "call_outcome": a.call_outcome, "call_summary": a.call_summary, "next_step": a.next_step, "follow_up_at": a.follow_up_at, "actor_name": by_id.get(a.actor_id, "System"), "created_at": a.created_at} for a in rows]


@app.post("/api/v1/leads/{lead_id}/activities", status_code=201)
def create_lead_activity(lead_id: str, payload: ActivityCreate, request: Request, db: DB, _auth: Auth):
    actor = _actor(request)
    if actor.get("role") == "readonly": raise HTTPException(status_code=403, detail="Read-only access")
    lead = db.scalar(_scoped(select(Lead).where(Lead.id == lead_id), Lead, actor))
    if not lead: raise HTTPException(status_code=404, detail="Lead not found")
    try:
        validate_follow_up_timestamp(payload.activity_type, payload.next_follow_up_at)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if payload.activity_type == "call":
        if not payload.call_summary:
            raise HTTPException(status_code=422, detail="A call summary is required for every logged call")
        if payload.status not in ("won", "lost") and payload.next_follow_up_at is None:
            raise HTTPException(status_code=422, detail="Set a next follow-up for every active lead after a call")
        if payload.next_follow_up_at and payload.next_follow_up_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=422, detail="Next follow-up must be in the future")
    summary = payload.call_summary or payload.message or None
    activity = LeadActivity(organization_id=lead.organization_id or actor.get("org"), lead_id=lead.id, actor_id=actor.get("sub"), activity_type=payload.activity_type, message=payload.message or summary or payload.activity_type.replace("_", " ").title(), call_outcome=payload.call_outcome, call_summary=summary if payload.activity_type == "call" else None, next_step=payload.next_step, follow_up_at=payload.next_follow_up_at)
    if payload.activity_type in ("call", "whatsapp", "email", "site_visit", "meeting"):
        lead.last_contact_at = datetime.now(timezone.utc)
    if payload.next_follow_up_at is not None:
        lead.next_follow_up_at = payload.next_follow_up_at
    elif payload.status in ("won", "lost"):
        lead.next_follow_up_at = None
    if payload.status is not None:
        lead.status = payload.status
    db.add(activity); db.commit(); db.refresh(activity)
    return {"id": activity.id, "activity_type": activity.activity_type, "message": activity.message, "call_summary": activity.call_summary, "call_outcome": activity.call_outcome, "next_step": activity.next_step, "follow_up_at": activity.follow_up_at, "created_at": activity.created_at}


@app.get("/api/v1/leads/follow-ups")
def list_follow_ups(request: Request, db: DB, _auth: Auth, overdue_only: bool = False, missing_only: bool = False, limit: int = Query(default=100, ge=1, le=200)):
    actor = _actor(request)
    now = datetime.now(timezone.utc)
    query = _scoped(select(Lead), Lead, actor)
    if missing_only:
        query = query.where(Lead.next_follow_up_at.is_(None), Lead.status.notin_(["won", "lost"]))
        return list(db.scalars(query.order_by(Lead.created_at.asc()).limit(limit)).all())
    query = query.where(Lead.next_follow_up_at.is_not(None))
    if overdue_only:
        query = query.where(Lead.next_follow_up_at < now)
    return list(db.scalars(query.order_by(Lead.next_follow_up_at.asc()).limit(limit)).all())



def _report_dates(start_date: date | None, end_date: date | None):
    try:
        return report_window(start_date, end_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _report_cohort_stage_count(db: Session, org_id: str, start_at: datetime, end_exclusive: datetime, condition) -> int:
    query = (
        select(func.count(func.distinct(LeadActivity.lead_id)))
        .join(Lead, Lead.id == LeadActivity.lead_id)
        .where(
            LeadActivity.organization_id == org_id,
            Lead.organization_id == org_id,
            Lead.created_at >= start_at,
            Lead.created_at < end_exclusive,
            LeadActivity.created_at >= start_at,
            LeadActivity.created_at < end_exclusive,
            condition,
        )
    )
    return int(db.scalar(query) or 0)


@app.get("/api/v1/reports/summary")
def reports_summary(
    request: Request,
    db: DB,
    _auth: Auth,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
):
    actor = _require_role(request, "admin", "manager")
    start_at, end_exclusive, start_day, end_day = _report_dates(start_date, end_date)
    org_id = actor["org"]
    now = datetime.now(timezone.utc)

    created_count = int(db.scalar(
        select(func.count(Lead.id)).where(
            Lead.organization_id == org_id,
            Lead.created_at >= start_at,
            Lead.created_at < end_exclusive,
        )
    ) or 0)

    contact_condition = or_(
        LeadActivity.activity_type.in_(["call", "whatsapp", "email", "meeting", "site_visit"]),
        and_(
            LeadActivity.activity_type == "status_change",
            LeadActivity.message.like("% to contacted"),
        ),
    )
    contacted_count = _report_cohort_stage_count(db, org_id, start_at, end_exclusive, contact_condition)
    qualified_count = _report_cohort_stage_count(
        db, org_id, start_at, end_exclusive,
        and_(LeadActivity.activity_type == "status_change", LeadActivity.message.like("% to qualified")),
    )
    won_count = _report_cohort_stage_count(
        db, org_id, start_at, end_exclusive,
        and_(LeadActivity.activity_type == "status_change", LeadActivity.message.like("% to won")),
    )
    lost_count = _report_cohort_stage_count(
        db, org_id, start_at, end_exclusive,
        and_(LeadActivity.activity_type == "status_change", LeadActivity.message.like("% to lost")),
    )

    pipeline_rows = db.execute(
        select(Lead.status, func.count(Lead.id))
        .where(Lead.organization_id == org_id)
        .group_by(Lead.status)
    ).all()
    stages = ["new", "contacted", "qualified", "site_visit", "negotiation", "won", "lost", "nurture"]
    current_pipeline = {stage: 0 for stage in stages}
    current_pipeline.update({stage: int(count) for stage, count in pipeline_rows if stage in current_pipeline})

    overdue_now = int(db.scalar(
        select(func.count(Lead.id)).where(
            Lead.organization_id == org_id,
            Lead.status.notin_(["won", "lost"]),
            Lead.next_follow_up_at.is_not(None),
            Lead.next_follow_up_at < now,
        )
    ) or 0)
    unscheduled_now = int(db.scalar(
        select(func.count(Lead.id)).where(
            Lead.organization_id == org_id,
            Lead.status.notin_(["won", "lost"]),
            Lead.next_follow_up_at.is_(None),
        )
    ) or 0)
    activity_count = int(db.scalar(
        select(func.count(LeadActivity.id)).where(
            LeadActivity.organization_id == org_id,
            LeadActivity.created_at >= start_at,
            LeadActivity.created_at < end_exclusive,
        )
    ) or 0)
    follow_up_count = int(db.scalar(
        select(func.count(LeadActivity.id)).where(
            LeadActivity.organization_id == org_id,
            LeadActivity.activity_type == "follow_up",
            LeadActivity.created_at >= start_at,
            LeadActivity.created_at < end_exclusive,
        )
    ) or 0)

    employees = db.scalars(
        select(Employee).where(Employee.organization_id == org_id).order_by(Employee.name.asc())
    ).all()
    lead_count_rows = db.execute(
        select(Lead.assigned_to, Lead.status, func.count(Lead.id))
        .where(Lead.organization_id == org_id, Lead.assigned_to.is_not(None))
        .group_by(Lead.assigned_to, Lead.status)
    ).all()
    counts_by_employee: dict[str, dict[str, int]] = {}
    for employee_id, lead_status, count in lead_count_rows:
        row = counts_by_employee.setdefault(employee_id, {})
        row[lead_status] = int(count)
    overdue_rows = db.execute(
        select(Lead.assigned_to, func.count(Lead.id))
        .where(
            Lead.organization_id == org_id,
            Lead.assigned_to.is_not(None),
            Lead.status.notin_(["won", "lost"]),
            Lead.next_follow_up_at.is_not(None),
            Lead.next_follow_up_at < now,
        )
        .group_by(Lead.assigned_to)
    ).all()
    overdue_by_employee = {employee_id: int(count) for employee_id, count in overdue_rows}
    activity_rows = db.execute(
        select(LeadActivity.actor_id, func.count(LeadActivity.id))
        .where(
            LeadActivity.organization_id == org_id,
            LeadActivity.created_at >= start_at,
            LeadActivity.created_at < end_exclusive,
        )
        .group_by(LeadActivity.actor_id)
    ).all()
    activity_by_employee = {employee_id: int(count) for employee_id, count in activity_rows if employee_id}
    team_rows = []
    for employee in employees:
        counts = counts_by_employee.get(employee.id, {})
        assigned_total = sum(counts.values())
        active_total = sum(count for stage, count in counts.items() if stage not in ("won", "lost"))
        team_rows.append({
            "id": employee.id,
            "name": employee.name,
            "role": employee.role,
            "active": employee.active,
            "assigned_leads": assigned_total,
            "active_leads": active_total,
            "qualified_leads": counts.get("qualified", 0),
            "won_leads": counts.get("won", 0),
            "lost_leads": counts.get("lost", 0),
            "overdue_follow_ups": overdue_by_employee.get(employee.id, 0),
            "activities_in_period": activity_by_employee.get(employee.id, 0),
        })

    def percentage(numerator: int, denominator: int) -> float:
        return round(numerator * 100.0 / denominator, 1) if denominator else 0.0

    return {
        "date_range": {
            "start_date": start_day.isoformat(),
            "end_date": end_day.isoformat(),
            "timezone": "Asia/Kolkata",
        },
        "cohort": {
            "leads_created": created_count,
            "contacted_leads": contacted_count,
            "qualified_leads": qualified_count,
            "won_leads": won_count,
            "lost_leads": lost_count,
            "conversion_percentages": {
                "created_to_contacted": percentage(contacted_count, created_count),
                "contacted_to_qualified": percentage(qualified_count, contacted_count),
                "qualified_to_won": percentage(won_count, qualified_count),
            },
            "definition": "Conversions count distinct leads created inside the selected date range with the matching activity/status transition also recorded inside that range.",
        },
        "current_pipeline": current_pipeline,
        "follow_up": {
            "follow_up_activities_in_period": follow_up_count,
            "all_activities_in_period": activity_count,
            "overdue_active_leads_now": overdue_now,
            "unscheduled_active_leads_now": unscheduled_now,
        },
        "team": team_rows,
    }


@app.get("/api/v1/reports/export.csv")
def export_reports_csv(
    request: Request,
    db: DB,
    _auth: Auth,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
):
    actor = _require_role(request, "admin", "manager")
    start_at, end_exclusive, start_day, end_day = _report_dates(start_date, end_date)
    org_id = actor["org"]
    rows = db.execute(
        select(Lead, Employee.name)
        .outerjoin(Employee, and_(Employee.id == Lead.assigned_to, Employee.organization_id == org_id))
        .where(
            Lead.organization_id == org_id,
            Lead.created_at >= start_at,
            Lead.created_at < end_exclusive,
        )
        .order_by(Lead.created_at.desc(), Lead.id.asc())
    ).all()
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow([
        "lead_id", "lead_name", "phone", "email", "locality", "property_type",
        "budget_min_inr", "budget_max_inr", "source", "stage", "assigned_employee",
        "created_at", "next_follow_up_at",
    ])
    for lead, employee_name in rows:
        min_budget = "" if lead.budget_min_paise is None else format(lead.budget_min_paise / 100, ".2f")
        max_budget = "" if lead.budget_max_paise is None else format(lead.budget_max_paise / 100, ".2f")
        writer.writerow([
            safe_csv_cell(lead.id),
            safe_csv_cell(lead.name),
            safe_csv_cell(lead.phone_e164),
            safe_csv_cell(lead.email),
            safe_csv_cell(lead.locality),
            safe_csv_cell(lead.property_type),
            safe_csv_cell(min_budget),
            safe_csv_cell(max_budget),
            safe_csv_cell(lead.source),
            safe_csv_cell(lead.status),
            safe_csv_cell(employee_name),
            safe_csv_cell(lead.created_at.isoformat() if lead.created_at else None),
            safe_csv_cell(lead.next_follow_up_at.isoformat() if lead.next_follow_up_at else None),
        ])
    filename = f"leadsrat-leads-{start_day.isoformat()}-to-{end_day.isoformat()}.csv"
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/api/v1/team/overview")
def team_overview(request: Request, db: DB, _auth: Auth):
    actor = _require_role(request, "admin", "manager")
    org_id = actor.get("org")
    users = db.scalars(select(Employee).where(Employee.organization_id == org_id).order_by(Employee.name.asc())).all()
    now = datetime.now(timezone.utc)
    result = []
    for user in users:
        assigned = select(Lead).where(Lead.organization_id == org_id, Lead.assigned_to == user.id)
        total = db.scalar(select(func.count()).select_from(assigned.subquery())) or 0
        new_count = db.scalar(select(func.count()).select_from(assigned.where(Lead.status == "new").subquery())) or 0
        qualified_count = db.scalar(select(func.count()).select_from(assigned.where(Lead.status == "qualified").subquery())) or 0
        stale = db.scalar(select(func.count()).select_from(assigned.where(Lead.status.notin_(["won", "lost"]), Lead.updated_at < now - timedelta(hours=48)).subquery())) or 0
        overdue = db.scalar(select(func.count()).select_from(assigned.where(Lead.next_follow_up_at.is_not(None), Lead.next_follow_up_at < now).subquery())) or 0
        presence = "online" if user.active and user.last_seen_at and user.last_seen_at >= now - timedelta(minutes=5) else ("recent" if user.active and user.last_seen_at and user.last_seen_at >= now - timedelta(minutes=30) else ("offline" if user.active else "suspended"))
        result.append({"id": user.id, "name": user.name, "email": user.email, "role": user.role, "active": user.active, "last_seen_at": user.last_seen_at, "presence": presence, "assigned_leads": total, "new_leads": new_count, "qualified_leads": qualified_count, "stale_leads": stale, "overdue_follow_ups": overdue})
    return {"employees": result, "totals": {"employees": len(users), "active_employees": sum(1 for u in users if u.active), "online_employees": sum(1 for u in result if u["presence"] == "online"), "assigned_leads": sum(x["assigned_leads"] for x in result), "stale_leads": sum(x["stale_leads"] for x in result), "overdue_follow_ups": sum(x["overdue_follow_ups"] for x in result)}}


@app.get("/api/v1/team/activity")
def team_activity(request: Request, db: DB, _auth: Auth, limit: int = Query(default=40, ge=1, le=100)):
    actor = _require_role(request, "admin", "manager")
    org_id = actor.get("org")
    rows = db.execute(select(LeadActivity, Lead.name, Lead.status, Employee.name).join(Lead, Lead.id == LeadActivity.lead_id).outerjoin(Employee, (Employee.id == LeadActivity.actor_id) & (Employee.organization_id == org_id)).where(LeadActivity.organization_id == org_id, Lead.organization_id == org_id).order_by(LeadActivity.created_at.desc()).limit(limit)).all()
    return [{"id": activity.id, "lead_id": activity.lead_id, "lead_name": lead_name, "lead_status": lead_status, "actor_name": actor_name or "System", "activity_type": activity.activity_type, "message": activity.message, "created_at": activity.created_at} for activity, lead_name, lead_status, actor_name in rows]


@app.get("/api/v1/team")
def list_team(request: Request, db: DB, _auth: Auth):
    actor = _require_role(request, "admin", "manager")
    if actor.get("role") == "service": raise HTTPException(status_code=403, detail="Use an organization-admin session")
    users = db.scalars(select(Employee).where(Employee.organization_id == actor["org"]).order_by(Employee.created_at.asc())).all()
    return [{"id": u.id, "name": u.name, "email": u.email, "role": u.role, "active": u.active, "last_seen_at": u.last_seen_at, "created_at": u.created_at} for u in users]


@app.post("/api/v1/team", status_code=201)
def create_team_member(payload: EmployeeCreate, request: Request, db: DB, _auth: Auth):
    actor = _require_role(request, "admin")
    email = payload.email.lower()
    if db.scalar(select(Employee.id).where(Employee.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = Employee(organization_id=actor["org"], name=payload.name, email=email, password_hash=_hash_password(payload.password), role=payload.role, active=True)
    db.add(user); db.commit(); db.refresh(user)
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role, "active": user.active, "created_at": user.created_at}


@app.patch("/api/v1/team/{employee_id}")
def update_team_member(employee_id: str, payload: EmployeeUpdate, request: Request, db: DB, _auth: Auth):
    actor = _require_role(request, "admin")
    user = db.scalar(select(Employee).where(Employee.id == employee_id, Employee.organization_id == actor["org"]))
    if not user: raise HTTPException(status_code=404, detail="Employee not found")
    if user.id == actor.get("sub") and payload.active is False: raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    if user.id == actor.get("sub") and payload.role is not None: raise HTTPException(status_code=400, detail="You cannot change your own role")
    if payload.role is not None: user.role = payload.role
    if payload.active is not None: user.active = payload.active
    if payload.password is not None: user.password_hash = _hash_password(payload.password)
    db.commit(); db.refresh(user)
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role, "active": user.active}


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE leads ADD COLUMN IF NOT EXISTS organization_id VARCHAR(36)"))
        conn.execute(text("ALTER TABLE leads ADD COLUMN IF NOT EXISTS assigned_to VARCHAR(36)"))
        conn.execute(text("ALTER TABLE leads ADD COLUMN IF NOT EXISTS last_contact_at TIMESTAMP WITH TIME ZONE"))
        conn.execute(text("ALTER TABLE leads ADD COLUMN IF NOT EXISTS next_follow_up_at TIMESTAMP WITH TIME ZONE"))
        conn.execute(text("ALTER TABLE properties ADD COLUMN IF NOT EXISTS organization_id VARCHAR(36)"))
        conn.execute(text("ALTER TABLE employees ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP WITH TIME ZONE"))
        conn.execute(text("ALTER TABLE lead_activities ADD COLUMN IF NOT EXISTS call_outcome VARCHAR(40)"))
        conn.execute(text("ALTER TABLE lead_activities ADD COLUMN IF NOT EXISTS call_summary TEXT"))
        conn.execute(text("ALTER TABLE lead_activities ADD COLUMN IF NOT EXISTS next_step TEXT"))
        conn.execute(text("ALTER TABLE lead_activities ADD COLUMN IF NOT EXISTS follow_up_at TIMESTAMP WITH TIME ZONE"))
        org = conn.execute(text("SELECT id FROM organizations WHERE slug='parkzone' LIMIT 1")).scalar()
        if not org:
            org = str(uuid.uuid4())
            conn.execute(text("INSERT INTO organizations (id, name, slug) VALUES (:id, :name, 'parkzone')"), {"id": org, "name": "ParkZone Realty"})
        conn.execute(text("UPDATE leads SET organization_id=:org WHERE organization_id IS NULL"), {"org": org})
        conn.execute(text("UPDATE properties SET organization_id=:org WHERE organization_id IS NULL"), {"org": org})
        existing = conn.execute(text("SELECT id FROM employees WHERE email=:email LIMIT 1"), {"email": ADMIN_EMAIL}).scalar()
        if not existing:
            conn.execute(text("INSERT INTO employees (id, organization_id, name, email, password_hash, role, active) VALUES (:id, :org, 'Workspace Admin', :email, :password_hash, 'admin', TRUE)"), {"id": str(uuid.uuid4()), "org": org, "email": ADMIN_EMAIL, "password_hash": _hash_password(ADMIN_PASSWORD)})


@app.get("/health/live", include_in_schema=False)
def live():
    return {"status": "ok"}


@app.get("/health/ready", include_in_schema=False)
def ready(db: DB):
    try:
        db.execute(select(1))
        return {"status": "ready", "database": "ok"}
    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable")


@app.get("/api/v1/dashboard", dependencies=[Depends(require_api_key)])
def dashboard(request: Request, db: DB):
    actor = _actor(request)
    lq = _scoped(select(Lead), Lead, actor); pq = _scoped(select(Property), Property, actor)
    lead_total = db.scalar(select(func.count()).select_from(lq.subquery())) or 0
    property_total = db.scalar(select(func.count()).select_from(pq.subquery())) or 0
    new_leads = db.scalar(select(func.count()).select_from(_scoped(select(Lead), Lead, actor).where(Lead.status == "new").subquery())) or 0
    qualified = db.scalar(select(func.count()).select_from(_scoped(select(Lead), Lead, actor).where(Lead.status == "qualified").subquery())) or 0
    return {"leads_total": lead_total, "properties_total": property_total, "new_leads": new_leads, "qualified_leads": qualified}


@app.post("/api/v1/leads", response_model=LeadOut, status_code=201, dependencies=[Depends(require_api_key)])
def create_lead(payload: LeadCreate, request: Request, db: DB):
    actor = _actor(request)
    if actor.get("role") == "readonly": raise HTTPException(status_code=403, detail="Read-only access")
    lead = Lead(**payload.model_dump(), organization_id=actor.get("org"), assigned_to=actor.get("sub") if actor.get("role") == "agent" else None)
    db.add(lead)
    db.flush()
    if lead.organization_id:
        db.add(LeadActivity(organization_id=lead.organization_id, lead_id=lead.id, actor_id=actor.get("sub"), activity_type="note", message="Lead created"))
    db.commit()
    db.refresh(lead)
    return lead


@app.get("/api/v1/leads", response_model=list[LeadOut], dependencies=[Depends(require_api_key)])
def list_leads(request: Request, db: DB, status_filter: str | None = Query(default=None, alias="status"), limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)):
    query = _scoped(select(Lead), Lead, _actor(request)).order_by(Lead.created_at.desc()).limit(limit).offset(offset)
    if status_filter:
        query = query.where(Lead.status == status_filter)
    return list(db.scalars(query).all())


@app.patch("/api/v1/leads/{lead_id}/status", response_model=LeadOut, dependencies=[Depends(require_api_key)])
def update_lead_status(lead_id: str, payload: StatusUpdate, request: Request, db: DB):
    actor = _actor(request)
    if actor.get("role") == "readonly": raise HTTPException(status_code=403, detail="Read-only access")
    lead = db.scalar(_scoped(select(Lead).where(Lead.id == lead_id), Lead, actor))
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    previous = lead.status
    lead.status = payload.status
    if payload.status == "contacted": lead.last_contact_at = datetime.now(timezone.utc)
    if "next_follow_up_at" in payload.model_fields_set: lead.next_follow_up_at = payload.next_follow_up_at
    actor = _actor(request)
    org_id = actor.get("org") or lead.organization_id
    if previous != payload.status:
