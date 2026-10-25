# 引文编号与数值输出约束 Implementation Plan

> Inline executing-plans, one final independent review and one important-fix pass if needed. User approves the proposed small reliability fix and one bounded real retest. No commit/push/deploy, production routing migration or historical score changes.

**Goal:** Prevent generated quote corruption and constrain decimal/unit output while retaining original strict scoring and all failed baselines.

**Design:** Add one compact versioned candidate module app/report_evidence_task.py. Model selects at most2 evidence IDs from exactly verified authorized source spans; server returns their original text and positions. No quote rewriting, fuzzy matching or dropping bad references. Candidate helper consumes trusted build_context plus already authorized fragments, never corpus/gold. Existing scoped source rules handle empty scopes through original make_task. Value must match plain decimal string grammar; commas/percent signs/exponents rejected, not corrected. Unit enum/prompt clarifies人民币 is currency, unit元; preserve magnitude and explicit per-share spelling, no server unit conversion or scoring aliases. Keep v1 task, scorer, retriever, frozen corpus/rawresults byte-identical.

## Tasks

- [x] TDD synthetic tests in tests/unit/test_report_evidence_task.py: exact known-position copying even for repeated text, IDs/raw quote/coordinate injection, unsupported decimal syntax, supported/insufficient consistency, bad or duplicate source coordinates, duplicate refs, wrong identity, invalid unit aliases, and correct citation failing wrong-value/unit scoring. Observe failure before new module exists, then green.
- [x] Implement the candidate module, retain v1 API and old saved-proposal tests. No active business route switch. Run new tests plus relevant task/gateway/boundary tests and full isolated unit suite (`--confcutdir=tests/unit`; root fixture truncates PostgreSQL).
- [x] Freeze v2 method/experiment artifacts before new calls. Reuse exact same36cases/hybrid top3 source spans, 24facts plus2generatedfuture and10programboundaries. Offline capture/scope validation, one real retest (max26actualattempts, pergroup24gatecalls/220000chars/480sec,1024output/request,30sec/request,0retries). New result directory; old results/gold/scorer unchanged. Raw candidate proposals retained alongside server-located answers.
- [x] One independent read-only review of code/result, important fixes only with RED→GREEN/full suite; no repeated paid runs. Save report with baseline20/24, v2 outcomes, sample limitations, protocol differences and next integration decision.

No new PDF/index/dependency/UI changes. This is evidence provenance plus output-contract work, not automatic proof of financial semantics or independently blind validation. Preserve uncommitted prior changes, recent cleanup and personal files.
