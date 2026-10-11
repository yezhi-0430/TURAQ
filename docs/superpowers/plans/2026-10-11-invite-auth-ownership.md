# Invite Email Authentication and Ownership Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the locally testable multi-user invite-registration, data isolation, confirmed action and quota baseline; real email and server provisioning are deferred at the user's explicit request.

**Architecture:** FastAPI dependencies identify actors from revocable database sessions and enforce CSRF. PostgreSQL owns identities, invitation counters, audit ownership and shared limits. The existing TURAQ frontend consumes relative API paths and never trusts model text as authorization.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, PostgreSQL, Argon2id, configurable SMTP, existing HTML/CSS/JavaScript and Vite.

**Spec:** docs/superpowers/specs/2026-10-11-invite-auth-ownership-design.md

## Global Constraints

- Passwords: 6–15 characters inclusive, not truncated or trimmed, same registration/reset rules.
- Invitations: reusable, default 50 activated accounts, 7-day expiry, revocable and adjustable; atomically consumed at email verification.
- No SMTP account/server purchase, production database migration, invitation sending, deployment, push or visibility change in this task.
- Protect every private original API as well as Agent action API; user identity comes only from the session. Foreign watchlist IDs return 404.
- Existing minute quotes and current frontend work must be retained. Never discard or commit unrelated baseline changes blindly.
- Read-only tools remain read-only. Suggestions never automatically become actions.
- Real email remains required before external registration; test mail transport cannot masquerade as production delivery.
- Implement tests RED then GREEN. Only the dedicated test database or isolated SQLite may be mutated.

## Task 1: Identity, email contracts, invitation transactions, ownership and action audit

**Files:** Create app/auth/{__init__,models,schemas,service,mail,dependencies,api,admin}.py and tests/auth/*; modify app/{config,database,main,agent_api,agent_actions,schema_upgrade}.py, app/{watchlists,audit}/repository.py, app/market_api.py, pyproject.toml and scoped test fixtures. Existing risk model integration is protected but budgets are Task 2.

**Interfaces produced:**

- GET /api/v1/auth/session returns `{user: {id,email,is_admin}|null, csrf_token: string, mail_configured: boolean}` and establishes an anonymous session if necessary.
- POST /auth/register `{email,password,invite_code}`; /auth/resend-verification `{email}`; /auth/forgot-password `{email}` return accepted/generic detail without tokens.
- POST /auth/verify-email `{token}` activates only once; invalid/full/expired invite does not create an active account. Support a replacement invite alongside a valid verification token.
- POST /auth/login `{email,password}` returns fresh session JSON; POST /auth/logout returns anonymous session JSON; POST /auth/reset-password `{token,password}` revokes old sessions.
- SMTP links use site base URL with `#verify=<token>` or `#reset=<token>`; links are actionable via POST, not destructive GETs.
- app.auth.dependencies.require_actor(request: Request) -> Actor(id:int,email:str,is_admin:bool), validates the session and CSRF on unsafe methods, sets request.state.actor. Protected endpoints add Depends(require_actor).
- All JSON writes send X-CSRF-Token; JSON-only, strict Origin/Sec-Fetch-Site checks and token checks include login/register/logout. Missing browser Origin in trusted same-origin tests is addressed explicitly, never a credential CORS wildcard.
- Existing watchlist API shapes and Agent action result shapes retained. Owned watchlist queries/commands receive explicit actor_id. Shared Stock cannot be overwritten from client metadata; new symbols may be resolved from the already available trusted quote source on the server, not from arbitrary client names.
- New HTTP tool audits and action audits bind actor_id; historical unattributed audits remain system-only.
- Explicit CLI migration accepts a designated verified owner, never auto-assigns old records to first registrant. CLI invitation management is restricted to the server operator; bootstrap is explicit.
- Throttle interface for Task 2: shared atomic limit storage under app/auth or a documented adapter. Login and mail limits must be implemented, not disabled pending budgets.

- [ ] Write isolated HTTP/service tests for password bounds, verification activation, invite exhaustion/revocation/race, reset/session revocation, CSRF, unverified/disabled users and SMTP errors. Representative behavioral assertion:

```python
def test_foreign_watchlist_not_accessible(client_b, watchlist_a):
    response = client_b.get(f"/api/v1/watchlists/{watchlist_a}/stocks")
    assert response.status_code == 404
```

- [ ] Run `.venv/Scripts/python.exe -m pytest tests/auth --confcutdir=tests/auth -q`; inspect expected pre-implementation collection/behavior failures.
- [ ] Implement focused models, services, mail transport and dependencies; transactionally activate accounts and revoke sessions. Integrate all original endpoint ownership checks and authenticated HTTP audit attribution. Add explicit migration/admin commands and dependency installation.
- [ ] Run the auth tests plus relevant isolated unit tests and PostgreSQL tests; adapt original fixtures to create authenticated test owners rather than weakening production guards.
- [ ] Self-review errors, source boundaries and migration behavior, run Ruff/diff checks, record commands/results and commit exact task files only.

## Task 2: Shared quotas, bounded model calls and deployment configuration preparation

**Files:** Create app/model_limits.py (or app/limits/*) and tests/auth/test_limits*.py; modify app/{agent_api,risk_api,llm_client,config}.py, schema registration and test fixtures as needed; update .env.example with scoped fields. Do not provision SMTP or a server.

**Consumes:** Task 1 actor dependency and real session factory; authenticated Agent/risk endpoints.

**Produces:** Request admission used by both model endpoints, per-call wrapper before actual model HTTP calls and releases/expiring leases in shared database storage.

- [ ] Write tests which verify rejection occurs before the client is called, rolling limits, owner separation, shared global counter, release after exception and safe lease expiry. Representative assertion:

```python
def test_quota_rejection_never_calls_model(client_a, exhausted_budget, model_spy):
    response = client_a.post("/api/v1/agent/chat", json={"messages": [{"role": "user", "content": "研究"}]})
    assert response.status_code == 429
    assert model_spy.calls == 0
```

- [ ] Run the new tests, confirm RED; implement PostgreSQL atomic counters/admission, rate limit handler with Retry-After and fail-closed model admission.
- [ ] Default user limits: 20 research requests/day, 2/minute, 1 concurrent; site 200 actual model attempts/day including retries, both endpoints. Bounds include maximum output tokens and finite HTTP/total processing time.
- [ ] Preserve 5-round tool cap; public errors cannot expose model credentials or internal exception details. Real model mode can be disabled without affecting watchlists/quotes.
- [ ] Check production settings against actual config, prepare same-origin API/secure cookies/trusted origins and required settings examples. Leave external setup explicitly deferred.
- [ ] Run behavioral and PostgreSQL concurrency tests, scoped Ruff, record evidence and commit exact files.

## Task 3: TURAQ account flows, safe API client and explicit suggestion confirmation

**Files:** Create frontend/auth.js, auth.css, api.js and tests/frontend/auth*.test.*; modify frontend/{index.html,market.js,market-detail.js,watchlist.js,vite.config.js,README.md} and build script registration. Preserve baseline appearance, animations and minute charts.

**Consumes:** Task 1 HTTP session/CSRF/auth/action contracts; Task 2 429/Retry-After. Existing suggestions contain operation=remove_watchlist_stock, watchlist_id, stock_code, text and status=suggested.

**Produces:** Browser registration/login/reset flows, account switch isolation, source cards and user-created ExecutionRequest.

- [ ] Write frontend behavior tests for private entry requiring login, authenticated CSRF writes, password bounds, cancel/no action, double-click suppression, rejection/error/unknown-outcome states and stale response isolation.
- [ ] Run new tests and confirm RED; implement a centralized same-origin API wrapper, session bootstrap and gold/dark account forms accessible on mobile.
- [ ] Render source dates accurately, structured suggestions as pending cards; load only owned target group and show exact effect in a confirmation dialog. Only final click sends `{kind:"execution_request",operation:"remove_watchlist_stock",watchlist_id,stock_code}`.
- [ ] Stop refresh/reset private caches and reject late responses on logout/account changes. Timeout is an unknown outcome, not automatic retry or success; 401 routes to login and 429 displays retry information.
- [ ] Run frontend tests/build and desktop/mobile browser visual acceptance using a separate fixture database and fake model/test mail, never production credentials or permanent demo users.
- [ ] Record verification and commit exact files. Update user-facing README/admin instructions to describe pending real email/server activation honestly.

## Task 4: Integration, independent review and final local acceptance

**Files:** docs/auth-local-acceptance.md, this plan progress and review packages; fixes restricted to findings.

- [ ] Run isolated unit suites and complete dedicated PostgreSQL suite, frontend tests and build. Inspect every result; use real PostgreSQL races for atomic invitation/quota claims.
- [ ] Package each task diff with its recorded BASE and task test evidence for read-only spec/quality review; fix covering failures RED→GREEN before accepting a task.
- [ ] Run independent whole-change review for privilege escalation, session/CSRF, client state, limits and migration. Do not duplicate reviews from implementers.
- [ ] Publish a local completion report distinguishing implemented/tested features from deferred SMTP/server setup and incomplete older learning items. No push or deployment.

## Execution ledger and decisions

- User explicitly requested immediate development without tutoring; there is no intermediate permission gate for routine implementation.
- Work in the existing checkout on a new codex/ branch so current uncommitted market/frontend work remains available; avoid a clean worktree that would omit required baseline files. Existing unrelated dirt must remain intact.
- SMTP implementation and test injection are in scope; obtaining an account, entering credentials, sending real email and deploying are deferred.
- Task order is sequential because shared backend contracts and frontend integration depend on prior work. One fresh implementer and task review per deliverable; controller coordinates, does not duplicate implementation.
