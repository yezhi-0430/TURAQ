# 修复后的财报真实回答验收 Implementation Plan

> Inline executing-plans; one independent final read-only result audit. User approved real model use after being told it consumes quota. No business integration, commit, push, deployment, source/scorer/gold/prompt changes or paid retries.

**Goal:** Measure numerical/unit/period/citation accuracy and future-period abstention using existing frozen hybrid top3 fragments for Midea, CMB and Yili.

**Design:** Reuse scripts.run_table_hybrid_eval.live_answers unchanged, including existing quote-only make_task, BoundedChat, ModelGate, strict score_answer and complete-denominator summaries. Read already frozen retrieval outputs, validate source coordinates/scope and fingerprints before sending. Separate known-regression22cases and fresh-issuer14cases,24factual requests and12boundaries;10boundaries handled by source rules,2future cases actually reach model. Same-author references and32physical pages/report; Yili is a first live-answer test, not an independently blind set. No reindex/reparse/retrieval tuning or rerun of historical systems. No new production code or deletion-mirroring tests; execution script is an experiment artifact.

**Budget:** Existing per-group gate:24calls,220000request characters,1024max output tokens/request,480seconds,30seconds/request,no retries. Fixed one-call task means at most17+9=26provider attempts overall; total ceilings440000chars/960seconds. If a limit is hit, preserve errors/full denominator, do not raise limits. Actual cost remains unknown; retain all reported usage and unknown-usage counts. Read existing qwen-plus/DashScope HTTPS configuration without outputting credentials. No Langfuse export or business DB access in this standalone experiment.

## Tasks

- [x] Preflight frozen20method hashes, both corpus manifests and retrieval-result input hashes, exact case-row sequence, named5boundary isolation/group, every source span. Confirm configuration enabled and fixed request counts. Save protocol and execution artifact hashes before live calls.
- [x] Offline diagnose exact outgoing request sizes using capture-only client and same make_task, no HTTP. Check program-only boundary answers with unchanged scorer; keep these distinct from generated answers. Run existing task/gateway/scorer/boundary tests with `--confcutdir=tests/unit` and no real services.
- [x] Execute existing live_answers once/group with exclusive new outputs. Save raw public proposals, per-case scores/errors, usage after each case; no repair or repeat on failures. Preserve frozen inputs before/after, both full denominators and explicit model-vs-program boundaries.
- [x] Post-run report by company and dimension, inspect failure proposals/returned source spans without modifying them, decide readiness. One independent result audit. Save report/verification and ledger; rerun broader tests only if production source changes (none planned).
