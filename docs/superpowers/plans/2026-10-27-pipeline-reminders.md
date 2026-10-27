# Pipeline and Reminder Center Implementation Plan

> **For agentic workers:** Implement task-by-task using the current session, verifying each task before continuing.

**Goal:** Add a responsive Kanban pipeline view and an in-app reminder center to Leadsrat, preserving existing lead workflows, authorization behavior, and production data.

**Architecture:** Extend the existing single-page frontend and reuse the existing lead status and follow-up API endpoints. Implement reminder bucketing as a pure JavaScript helper for predictable timezone-boundary testing; do not add tables, migrations, external services, or new dependencies.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, vanilla JavaScript/HTML/CSS, Python tests, Node.js built-in test runner, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-10-27-pipeline-reminders-design.md`

## Global Constraints

- Preserve production database contents and avoid test writes against the live database.
- Keep `.env`, credentials, tokens, and lead/employee records out of GitHub.
- Preserve all existing stage values: `new`, `contacted`, `qualified`, `site_visit`, `negotiation`, `won`, `lost`, `nurture`.
- Keep existing table/search workflows and follow-up validation.
- Reuse server-side role and tenant authorization; front-end hiding is not an access-control boundary.
- First slice is in-app reminders only; do not claim browser push, email, SMS, or WhatsApp delivery.
- Do not deploy or restart production as part of feature implementation; use a reviewed PR and explicit deployment verification.

## Review Focus

1. A lead moved to a stage must persist on reload, and unauthorized/read-only roles must not mutate stage status.
2. A timestamp at the local start/end of day must enter the correct reminder bucket; invalid timestamps must not crash rendering.
3. Leads without follow-up dates must appear as unscheduled but won/lost leads must not.
4. A follow-up reschedule must use the existing authorized activity endpoint and must be strictly in the future.
5. Empty data, API failure, long lead names, and mobile-width layouts must remain understandable and usable.

---

### Task 1: Add behavior tests for reminder bucketing and existing frontend invariants

**Files:**
- Create: `tests/frontend_features.test.js`
- Modify: `.github/workflows/ci.yml`
- Test: `tests/test_frontend_navigation.py`

**Interfaces:**
- Produces pure helper `reminderBucket(timestamp, now = new Date())` returning `overdue`, `today`, `upcoming`, or `invalid`; absent timestamp is handled by the unscheduled view, not by this helper.

- [ ] Write Node built-in tests for overdue, due-today, upcoming, local midnight/day boundary, and invalid dates by extracting the pure helper from the HTML source.
- [ ] Run `node --test tests/frontend_features.test.js`; verify it fails before the helper is added.
- [ ] Add Python source guard tests for board stages, reminder navigation targets, and accessible non-drag stage controls.
- [ ] Run the new tests and verify they pass once the helper and UI IDs exist.

### Task 2: Implement the responsive pipeline board while preserving the table

**Files:**
- Modify: `app/static/index.html`
- Test: `tests/test_frontend_navigation.py`
- Test: `tests/frontend_features.test.js`

**Interfaces:**
- `renderLeads()` remains the filtered-data entry point and calls `renderPipelineBoard(filteredLeads)`.
- `updateLeadStage(leadId, status)` sends `PATCH /api/v1/leads/{id}/status` with the existing status contract and refreshes server state after success.
- `renderPipelineBoard(filteredLeads)` renders the eight existing stages and an accessible stage selector per card.

- [ ] Add failing tests asserting all stages, board/table toggles, and keyboard-operable stage selection.
- [ ] Implement compact responsive board columns, a visible item count for each stage, lead cards with relevant buyer details, and an accessible status select.
- [ ] Keep search/status filters consistent between board and table; keep table view available.
- [ ] Verify a stage change uses the API and that failed API requests show an error without pretending the transition saved.
- [ ] Run frontend tests, Python guards, and JavaScript syntax checks.

### Task 3: Implement the in-app reminder center

**Files:**
- Modify: `app/static/index.html`
- Test: `tests/frontend_features.test.js`
- Test: `tests/test_frontend_navigation.py`

**Interfaces:**
- `loadReminderCenter()` loads `GET /api/v1/leads/follow-ups?limit=200` and `GET /api/v1/leads/follow-ups?missing_only=true&limit=200`, then calls `renderReminderCenter(scheduled, unscheduled, now)`.
- `reminderBucket(timestamp, now = new Date())` uses browser-local calendar-day boundaries to return `overdue`, `today`, `upcoming`, or `invalid`.
- `openReminderModal(leadId)` records rescheduling via `POST /api/v1/leads/{id}/activities` using `activity_type: follow_up` and a future `next_follow_up_at`.

- [ ] Add failing tests for reminder navigation, all four buckets, future-date validation, and activity endpoint usage.
- [ ] Add role-aware navigation and reminder sections for overdue, due today, upcoming, and unscheduled follow-ups.
- [ ] Add explicit loading, empty, and API-error states and a record-activity/reschedule action per reminder.
- [ ] Validate selected follow-up times are future; refresh server data after save.
- [ ] Verify the employee and admin views continue to use the same session-scoped API.

### Task 4: Full verification and handoff

**Files:**
- Test: all tests and CI workflow
- Modify: documentation only if implementation differs from the spec

- [ ] Run Python regression tests, Node frontend tests, Python compile, JavaScript syntax check, manifest JSON check, Docker build, Compose config validation, and existing smoke checks.
- [ ] Inspect the diff for accidental secrets, production data, new dependencies, broken accessibility controls, and changes outside the first slice.
- [ ] Publish the reviewed changes on the feature branch and wait for CI evidence.
- [ ] Confirm the production page/readiness endpoints remain healthy and that no production deployment occurred during implementation.
