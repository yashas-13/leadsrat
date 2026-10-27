# Leadsrat Pipeline and Reminder Center — Design Spec

**Date:** 2026-10-27  
**Status:** Awaiting user approval  
**Repository:** `yashas-13/leadsrat`

## Intent

Improve the daily real-estate sales workflow without destabilizing the currently deployed Leadsrat app or losing existing CRM data. Ship small, testable slices: first a visual pipeline and an in-app reminder center; next reporting/CSV export; then assignment and team-workflow improvements.

## What exists today

- FastAPI API and PostgreSQL persistence, deployed with Docker Compose.
- The lead status vocabulary already includes `new`, `contacted`, `qualified`, `site_visit`, `negotiation`, `won`, `lost`, and `nurture`.
- The admin frontend displays pipeline counts as bars and leads in a table. Status changes use the existing status-update API.
- Follow-up dates are stored on leads. `GET /api/v1/leads/follow-ups` supports overdue and missing-follow-up filters; employee home lists due and unscheduled work.
- Role-aware sessions, agent assignment, activity history, and workload metrics are already implemented.
- The production app has data that must remain intact. The public repo was first synchronized through PR #1; the live service was not restarted as part of that sync.

## Approaches considered

1. **Incremental feature slices (selected):** add the visual pipeline and reminder center on the existing endpoints, then add reporting/export, then team assignment refinements. This limits risk and makes each slice independently testable.
2. **Reminders/reporting first:** would help managers but leave the pipeline's primary stage workflow unchanged.
3. **Single coordinated release:** covers all requested areas sooner on paper, but increases regression scope and makes production rollback harder.

## First implementation slice: pipeline + reminder center

### Pipeline board

- Add an admin/manager pipeline view grouping leads by the existing eight statuses.
- Show lead identity, locality/property type, budget, assigned employee (when available), and next follow-up where present.
- Allow a user to move a lead between stages through an explicit stage control; use the existing status endpoint, not direct frontend-only state mutation.
- Provide an accessible non-drag alternative (keyboard/screen-reader usable stage selector); drag-and-drop is optional and must not be the only interaction.
- Preserve existing table/search/filter workflows. Do not silently change or rename status values.
- Respect server-side role and tenant checks. Read-only users cannot change stages.

### In-app reminder center

- Provide clear lists for overdue, due today, upcoming, and unscheduled follow-ups, using the saved follow-up timestamps and the existing follow-ups API.
- Give each reminder a route to the relevant lead/activity workflow; allow scheduling/rescheduling only through existing authorized APIs and validate future dates.
- Make empty/error/loading states explicit. Show the current user's assigned records on the employee portal and organization records only to authorized admin/manager users.
- This slice is in-app reminders only. Do not claim background push, SMS, WhatsApp, or email delivery.

## Subsequent slices

1. **Reporting:** server-backed date-range counts and stage conversion, win/loss and follow-up performance, team workload metrics, plus CSV exports with bounded filters and correct authorization.
2. **Team workflow:** unassigned queue, bulk assignment, workload balancing, and regression tests for agent/manager/admin/read-only access and cross-organization isolation.

## Constraints and non-goals

- Preserve production database contents; no destructive migration, database reset, or test writes to the live database.
- Keep secrets, `.env`, credentials, session tokens, and customer/lead records out of GitHub.
- Use existing FastAPI, SQLAlchemy, PostgreSQL, single-file frontend, and Compose conventions unless testing proves a structural change is required.
- Do not introduce external notification providers, paid services, or new required secrets in the first slice.
- Do not deploy directly from an unreviewed branch. CI and the feature-specific tests must pass; deploy using a known-good rollback path and verify the live page/API after deployment.
- Do not combine source synchronization, schema redesign, RLS rollout, password recovery, and these UI features into one high-risk release.

## Acceptance criteria

- Board totals agree with the status-filtered API data; zero-count stages remain visible.
- A stage change persists across reload and records the existing activity/history behavior.
- Reminder buckets correctly distinguish overdue, due today, upcoming, and missing follow-ups under the app's agreed timezone handling.
- Agent views remain restricted to assigned leads; read-only access cannot mutate; admin/manager access remains organization-scoped.
- Automated tests cover status-stage rendering/updates, reminder bucketing and date boundaries, and authorization failures.
- Frontend JavaScript syntax, Python compilation, unit/regression tests, manifest validation, Docker build, and existing smoke tests pass.
- Production database counts and representative functionality are verified before and after release; rollback does not delete lead or activity data.

## Decisions left to the implementer

- Prefer a compact responsive Kanban with horizontally scrollable columns on mobile; keep the table view available.
- Treat date/time bucketing consistently in the browser's local timezone for display, but compare canonical timestamps in the backend where practical. Document any existing timezone limitations rather than silently changing stored values.
- Add no database tables for the first slice unless code inspection reveals that existing fields/endpoints cannot represent the required behavior.
