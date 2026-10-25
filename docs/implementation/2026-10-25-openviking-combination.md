# OpenViking combination implementation plan

> Execute inline with superpowers:executing-plans. User approved combining OpenViking with the existing application.

**Goal:** Use native OpenViking storage and file retrieval for known public report contexts and explicitly saved research preferences, retaining application evidence validation, strict scoring and model admission.

**Architecture:** Opt-in loopback-only adapter, native account per authenticated actor. Public source pages are content addressed, read back and compared exactly before application ranking; native file grep supplies candidates. On missing, changed, empty or unavailable retrieval, retain the existing source selector. Preferences are a small typed record, never extracted from chats; only enumerated presentation choices enter the agent prompt as user data.

**Scope decision:** First production combination uses native file operations and grep, not semantic find/search or session commit. Deferred batch writes schedule no vector or summary jobs. The dedicated service has a rejecting model endpoint and no cloud credentials. This delivers persistent context with no hidden provider attempts; semantic search remains a separate measured improvement.

**Constraints:** Do not modify frozen experiment methods, scores, corpora or historical OpenViking workspaces. No private document/chat ingestion. No migration or deletion of business databases. Tests use `--confcutdir=tests/unit` or the auth-specific equivalent. No commits or publication. Existing dirty workspace retained because its untracked application modules are required.

## Task 1: Scoped context adapter and application wiring

Files: new `app/context_store.py`, `app/context_api.py`; modify `app/config.py`, `app/main.py`, `app/agent_api.py`, `app/analysis/evidence.py`, `app/analysis/evaluation.py`. Tests: `tests/unit/test_context_combination.py`.

- [x] Test disabled/offline fallback, strict loopback configuration, native account isolation, deferred writes, exact source validation, current context allowlists and bounded operations.
- [x] Implement native adapter with generic credential-free errors, typed preference CRUD and no arbitrary caller-controlled paths.
- [x] Wire source retrieval into the existing evaluation selector and explicit preferences into agent messages; retain strict scorer and admitted model client.
- [x] Add authenticated/CSRF-protected preference endpoints and safe status metadata; verify invalid/disabled/offline behavior.

## Task 2: User controls, dedicated service and acceptance

Files: new `frontend/context-memory.js`, `scripts/launch_context_store.py`; modify `frontend/index.html`, `frontend/settings.js`, `.env.example`; new tests, operator guide and result record.

- [x] Test preference controls/session changes and local service ownership/configuration.
- [x] Add a research settings card with explicit save, refresh and clear actions; no browser persistence.
- [x] Launch dedicated pinned OpenViking 0.5.2 storage on loopback with all model traffic rejected; configure local opt-in without exposing keys.
- [x] Prove real storage read/write, grep, restart persistence, actor isolation, tampered body fallback and no provider calls using synthetic preferences plus known public report pages.
- [x] Run relevant and full safe unit/frontend/build verification; verify frozen method hashes.
- [x] One independent review of the final changes; fix Critical/Important once with regression tests, record Minor findings.

Acceptance distinguishes native integration proof from model accuracy. No new accuracy claims or reinterpretation of earlier experiment results.
