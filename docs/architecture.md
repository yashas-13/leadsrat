# Leadsrat Architecture

## User experiences
- Organisation admin/manager web dashboard: `/leadsrat/admin` redirects to the portal-aware login. It presents team workload, recent authenticated activity, lead status, stale leads and overdue follow-ups.
- Employee/field workspace: `/leadsrat/employee` opens the mobile portal. It includes assigned lead cards, direct call/WhatsApp links, activity notes, status updates and follow-up dates.
- The login API validates the account role against the requested portal. UI hiding is convenience only; backend authorization remains authoritative.
- PWA manifest/icon support mobile installation. Service worker caches a small public application shell only; `/leadsrat/api/` responses and private lead data are never cached.

## Runtime
- FastAPI application: `app/main.py`
- PostgreSQL 16: source of truth
- Docker Compose deployment: `compose.yaml`
- API binds to `127.0.0.1:8787`; PostgreSQL has no published host port.
- Application container runs as non-root, read-only filesystem, drops Linux capabilities.
- Public app: `https://parkzone.in/leadsrat/`; docs: `https://parkzone.in/leadsrat/docs`.

## Identity and roles
- `organizations`: tenant/workspace metadata
- `employees`: named account, PBKDF2-HMAC-SHA256 password hash, role, active flag and last authenticated activity time
- `leads`: organization, assigned agent, last contact and next follow-up fields
- `lead_activities`: timestamped lead history, activity type, actor and message
- Session token is HMAC-signed and held in a Secure, HttpOnly, SameSite=Strict cookie with an eight-hour expiry
- Roles: `admin`, `manager`, `agent`, `readonly`
- Admins create employees, change roles and suspend/reactivate accounts; managers can view the team and assign leads; agents see assigned leads; read-only accounts cannot create/update records.
- Admin presence labels are based on authenticated app activity: online if seen within 5 minutes, recent within 30 minutes, otherwise offline. This is not location tracking or proof of physical presence.

## Operational endpoints
- `GET /admin`, `GET /employee`: portal entry redirects
- `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/session`
- `GET /api/v1/team`, `POST /api/v1/team`, `PATCH /api/v1/team/{employee_id}`
- `GET /api/v1/team/overview`, `GET /api/v1/team/activity`
- `GET /api/v1/dashboard`
- `POST /api/v1/leads`, `GET /api/v1/leads`, `PATCH /api/v1/leads/{id}/status`, `PATCH /api/v1/leads/{id}/assign`
- `GET/POST /api/v1/leads/{id}/activities`, `GET /api/v1/leads/follow-ups`
- `POST /api/v1/properties`, `GET /api/v1/properties`
- `GET /api/v1/leads/{id}/matches`
- `GET /health/live`, `GET /health/ready`

## Remaining production gates
1. Replace startup `create_all`/additive schema updates with versioned Alembic migrations.
2. Add PostgreSQL RLS and automated cross-tenant isolation tests; employee-session queries are currently scoped in app code.
3. Replace the global privileged API key with narrowly scoped integration credentials; service-key requests bypass employee-level tenant scoping by design.
4. Add login rate limiting/lockout, CSRF review, security headers, secure password reset/first-login and invitation flows.
5. Add automated positive login/CRUD, role authorization and browser E2E tests; add CI, monitoring and encrypted backup/restore drills.
6. Add consent/retention controls and reviewed incident/recovery runbooks before large-scale onboarding.

## Matching
Matching is deterministic and filters available inventory by exact locality/type and optional budget range. It is not a probabilistic intent model; inventory reliability depends on recent verification.
