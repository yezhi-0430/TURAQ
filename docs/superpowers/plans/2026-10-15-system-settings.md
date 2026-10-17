# System Settings Implementation Plan

> Use subagent-driven-development for the isolated backend task and requesting-code-review for final review. Current dirty feature checkout is the required working baseline.

**Goal:** Complete a role-aware, persisted settings center connected to existing modules.
**Architecture:** Personal JSON settings with typed validation; global overrides with optimistic version checks and audit entries. Runtime settings merge environment with stored overrides. Dedicated frontend controller renders user/admin forms and applies preferences to existing modules.
**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, plain JavaScript, Vite, pytest, Node tests.

## Global constraints
Preserve existing changes; no resets, blanket commits, deployment, or destructive data cleanup. Backend guards all privileged operations. No secrets in exports or audit. Save with revision and reject stale updates with HTTP 409.

## Task 1: Settings backend and runtime consumers
- [ ] Write API tests for GET/PUT personal and admin settings, role checks, validation, version conflicts, runtime overrides, password/session security.
- [ ] Run `.venv/Scripts/python -m pytest tests/auth/test_settings.py` and establish red.
- [ ] Add `app/user_settings/` models, schemas, service and API; register models/router. Routes use existing dependency-injected session factory and actor.
- [ ] Integrate model admission/clients, risk tasks and paper-account cap with global settings.
- [ ] Run new tests and affected auth/model suites, verify green.

Interface: `/api/v1/settings` GET returns `{preferences, defaults, version, account}`; PUT `{preferences, version}` returns the same. `/api/v1/admin/settings` GET returns `{values, defaults, version, secrets, diagnostics}`; PUT `{values, version}` returns same. Additional `/settings/password`, `/settings/sessions`, `/settings/sessions/revoke-others`, `/admin/settings/audit`, `/admin/settings/secrets`. All POST/PUT use existing CSRF.

## Task 2: Complete frontend with real preference consumers
- [ ] Test defaults, form parsing, JSON import and account-reset behavior with Node tests.
- [ ] Add `frontend/settings.js`, `frontend/settings.css`, replace placeholder, include build assets.
- [ ] Connect market polling, detail charts, watchlist sorting, chat keyboard/round limit, risk filters and paper-trading defaults/polling.
- [ ] Run Node tests and Vite build.

## Task 3: Verification and review
- [ ] Run backend and frontend regression suites.
- [ ] Inspect desktop/mobile settings, basic user and admin views, save/error/conflict/restore states in browser.
- [ ] Request independent security/correctness review scoped to new settings work; fix material findings with tests.
- [ ] Document deployment/migration, key setup and verified limitations; update this checklist with evidence.
