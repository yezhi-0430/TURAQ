# 证据编号接入评测接口 Implementation Plan

> Inline executing-plans; one final independent read-only review, important fixes in one RED→GREEN pass if required. User continued after candidate23/24 and proposed unit-policy/business integration step. No commit/push/deploy, business DB/index migration, gold/scorer/historical changes or new paid experiment.

**Goal:** Use source-evidence-ids-v2 in the existing authenticated exact-known-PDF evaluation endpoint, preserving strict scores and separately explaining equivalent unit labels.

**Design:** Add app/analysis/evidence.py adapter: select at most3 exact table/narrative units from only trusted context pages using existing pure BM25/financial-label functions, budget4800chars/20parts; no embedding downloads/dependency changes. This is explicit document-bm25-source-spans-v1, different from the CLI hybrid experiment, so do not transfer23/24 quality claims. Factory tracks decisions for existing trace counters and delegates empty-source exclusions to original fact_task. Existing admission, runtime-error stop/partial responses and usage accounting stay in place.

Add app/analysis/units.py after-score metadata: only finite equal numeric values with correct identity/evidence/support can receive unit-label equivalence. Allow人民币元↔元,元／股↔元/股, and only basic/diluted EPS元↔元/股; never scale magnitudes or remove commas/percent signs. Return raw/reference units and reason/policy version; do not change answer/scores/passed. UI displays a plain text note beside affected cases, not an alternative pass total.

## Tasks

- [x] TDD source selector + task factory (authorized source slices, budgets, deterministic ordering, no gold, no model for exclusions, strict v2 IDs); pure unit-label guard cases including wrong amounts/metrics/evidence/magnitude and unchanged strict scoring. Meaningful negative synthetic cases, no implementation-mirroring tests.
- [x] Integrate adapter in app/analysis/evaluation.py; preserve same dependencies/trace/deadline/quota/partial errors. Update existing isolated fake model fixture to understand v2 payload, retaining old assertions. Verify original known-corpus7facts all have located allowed evidence with same gold; describe selected-context gate separately from model accuracy.
- [x] Add frontend safe-text note + regression proving strict headline/scores unchanged and hostile labels not rendered as markup. No redesign or dependency changes.
- [x] Full isolated unit,29auth/limit/deadline/access,frontend suite/build/assets,Ruff/compile; no PostgreSQL fixture or real model. Reuse saved CMB v2 response to record strict failure plus unit-equivalent note, never rescore as pass.
- [x] One independent code/integration review, important-only fixes with tests if necessary. Save scoped report/verification and old52method/input fingerprint proof. No claim of new real API/model acceptance or deployed quality.
