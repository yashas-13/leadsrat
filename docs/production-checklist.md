# Leadsrat Production Checklist

## Deployed behaviour
- [x] Separate organisation-admin and employee login portals
- [x] Admin web dashboard with employee workload, last activity/presence, lead statuses, stale leads, overdue follow-ups and recent lead activity
- [x] Mobile-first employee workspace with assigned leads, call/WhatsApp links, activity notes, status updates and follow-up dates
- [x] PWA manifest, app icon, install prompt when supported and static-shell service worker cache (no authenticated API/private-data caching)
- [x] Named employee accounts and roles (`admin`, `manager`, `agent`, `readonly`)
- [x] Organization-scoped employee-session lead/property queries and server-side role checks
- [x] Docker Compose configuration validates, image builds, API/DB health checks pass
- [x] Unauthenticated protected API and team endpoints return HTTP 401
- [x] Python compile, frontend JavaScript parse, manifest JSON parse and `git diff --check` pass

## Required before broad production onboarding
- [ ] Versioned Alembic migrations; retire startup schema mutation
- [ ] PostgreSQL Row-Level Security and automated cross-tenant isolation tests
- [ ] Replace privileged global API key with narrowly scoped service credentials
- [ ] Login rate limiting, throttling and lockout monitoring
- [ ] CSRF review, security headers and structured audit logs for admin/assignment actions
- [ ] Password change/reset, employee invitation and secure first-login flow
- [ ] Automated positive login/CRUD and role-based authorization tests
- [ ] Browser E2E tests on Android Chrome and desktop browser, including PWA installation
- [ ] Encrypted off-site backups and a proven restore
- [ ] Monitoring, incident/recovery runbooks, consent/retention and DPDP review

## Presence semantics
- Online: authenticated session made a request in the last 5 minutes.
- Recent: authenticated session made a request in the last 30 minutes.
- Offline: account active but no recent application activity. A user with a suspended account is shown as suspended.
- These are application-activity indicators, not GPS or guaranteed physical presence.

## Rollback
- Keep the last known-good image tag.
- Back up the database before schema changes.
- The current migration uses additive columns/new tables; preserve existing database records when rolling back the application image.
- Use a reviewed database recovery plan for destructive changes.
