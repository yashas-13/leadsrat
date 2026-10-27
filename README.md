# Leadsrat — Real-estate CRM

Production-style beta deployment: `https://parkzone.in/leadsrat/`.

## Separate portal entry points

- **Organisation admin / manager web dashboard:** `https://parkzone.in/leadsrat/admin`
- **Employee mobile workspace:** `https://parkzone.in/leadsrat/employee`
- **Default portal chooser:** `https://parkzone.in/leadsrat/`
- **API documentation:** `https://parkzone.in/leadsrat/docs`

Portal choice is checked by the login API against the account role. Admin/manager accounts cannot sign in through the employee portal, and agent/read-only accounts cannot sign in through the admin portal. The organisation-admin dashboard includes employee presence based on recent authenticated activity, lead workload, new/qualified leads, stale leads, overdue follow-ups, and a recent lead-update feed. Admins can create employee records in PostgreSQL, choose an agent/manager/read-only role, and receive a one-time access card with the mobile login URL, email and temporary password to share privately. Employee account creation is persisted immediately; passwords are stored as PBKDF2 hashes, never as plaintext. Duplicate or malformed work email addresses are rejected. The employee view is mobile-first and supports assigned-lead management, tap-to-call, WhatsApp launching, status updates, activity notes, scheduled follow-ups, and PWA home-screen installation on supported browsers.

## Team and lead capabilities

- Named employee accounts with PBKDF2-HMAC-SHA256 password hashes and signed, Secure, HttpOnly, SameSite=Strict sessions (eight-hour expiry).
- Roles: `admin`, `manager`, `agent`, `readonly`.
- Admins create employee accounts, change roles and suspend/reactivate them. Managers can see team workload and assign leads. Agents are scoped to their assigned leads. Read-only accounts cannot make changes.
- Lead activity history records creation, assignment, status changes, notes, calls, meetings, email, WhatsApp actions and site visits that employees explicitly log.
- Follow-up timestamps and per-employee overdue/stale counts are exposed in the admin team report.
- PWA manifest and custom icon support a standalone mobile home-screen launch. The service worker caches only the public shell; it deliberately never caches authenticated API responses or lead data.
- PostgreSQL data storage; Docker Compose; API is bound to `127.0.0.1:8787`, and PostgreSQL is private to the Compose network.

## Sign-in and employee setup

The bootstrap administrator email defaults to `admin@parkzone.in`; the initial password is stored as `LEADSRAT_ADMIN_PASSWORD` in `/opt/leadsrat/.env` (file mode 0600). Never expose that value or `LEADSRAT_API_KEY`. Employees sign in using the work email and password created by the administrator at **Employee team → Add employee**. Use a unique temporary password of at least 12 characters and deliver it through a secure channel.

Employee self-service password change/reset, email invitations, and forced temporary-password rotation are not implemented yet. To rotate the bootstrap password, update `.env` and recreate the container:

```bash
cd /opt/leadsrat
sudoedit .env
docker compose up -d --build
```

## Build and smoke test

```bash
cd /opt/leadsrat
python3 -m py_compile app/main.py
node -e "const fs=require('fs');new Function(fs.readFileSync('app/static/index.html','utf8').match(/<script>([\\s\\S]*?)<\\/script>/)[1])"
python3 -m json.tool app/static/manifest.webmanifest >/dev/null
docker compose config -q
bash tests/smoke.sh
curl -fsS https://parkzone.in/leadsrat/health/ready
```

## Production hardening still required

This is not yet a fully hardened, multi-tenant SaaS. Before broad customer onboarding, replace additive startup schema updates with versioned Alembic migrations, add PostgreSQL Row-Level Security and cross-tenant tests, restrict or replace the server-side global API key (it deliberately bypasses employee-level tenant scoping), implement login rate limiting and lockout, complete CSRF/security-header review, audit admin changes, and add password reset/first-login flows. Add end-to-end browser tests, encrypted off-site backups and restore drills, monitoring, consent/retention controls, and a reviewed incident/recovery runbook. Presence is based on recent app activity, not GPS or guaranteed physical presence. PWA support varies by browser; where no install prompt appears, use the browser menu’s **Add to Home Screen** action.

Monetary API fields are integer paise; the frontend accepts rupees and converts them before submission.
