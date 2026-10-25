# 财报表格上下文与混合检索 Implementation Plan

> Inline execution using superpowers:executing-plans, with one independent final read-only reviewer. User approved the preceding next step by “继续”. Existing uncommitted work remains; no commit, push, deployment or business-index migration.

## Design and scope

Goal: improve retrieval of annual-report facts without changing gold, scorer, source boundaries or the quote-only model task. Adopt table-row units with separate original header excerpts, lexical BM25 plus local BGE cosine retrieval, reciprocal-rank fusion and deterministic reranking. Keep this experimental candidate separate from production RAG and all historical results. Alternatives: only larger fixed windows preserve more context but dilute ranking; replacing the embedding model adds runtime cost without repairing table structure. Neither is selected.

Rows and headers retain independent exact source start/end coordinates. Never concatenate separated excerpts into a purported original quote. Search text may join/normalize header and row for ranking; model-visible excerpts must remain separate literal original slices. Include fallback source-slices-v2 chunks so narrative text is covered. Detect row structure using line and numeric patterns, not company/page/answer/case identifiers. General financial-label aliases are versioned and include common terms beyond the benchmark. No gold or hidden full page enters ranking or generation.

Retrieve only explicitly caller-authorized resources, with owner/security/publication/report/version filters applied before either lexical or dense ranking. Dense vectors are loaded locally/offline; missing/invalid vectors must not become strong evidence. BM25 uses whitespace-normalized CJK bigrams plus Latin/numeric terms and common instruction stop terms. Financial-label coverage provides a deterministic rerank signal; it does not extract or certify values. Fuse top12 lexical and top12 cosine ranks with fixed k=60, deduplicate identical/overlapping body excerpts, return top3 units, max4800 visible characters including separate headers (max800/header,500/body). Long numeric rows fall back to bounded original slices.

Evaluate a fixed candidate and lexical-only ablation on the same 48 pages/20 cases. Report top1/top3 by evidence-unit rank; report visible chars/parts and compare context size honestly with old 500-char chunks and full-page comparators. A header can carry evidence, so metrics inspect the actual visible parts in each unit. Preserve all denominator cases and all scope abstentions. Gold is used only after retrieval for metrics, never passed to the retriever. This is a known diagnostic corpus, not a held-out test.

One bounded real answer run is allowed only if hybrid top3 reaches at least9/14, no retrieval/source errors, and all five scope boundaries remain empty. Same immutable prompt/task/scorer; <=24 calls,220000 request chars,1024 output tokens,480sec. No retries or schema repairs. Otherwise spend no model calls and explain the failed retrieval gate. No OpenViking server, cloud embeddings, new dependencies, frontend edits or business routing change.

## Tasks

- [x] Task1 TDD original row/header units: wrapped labels, adjusted/prior columns, quarters, two tables, long/noisy lines, fallback text, exact spans/coverage/limits.
  - New app/rag/table_chunks.py exposes table_units(text)->list[dict] with body span, header spans, search_text and kind; version table-rows-v1.
  - Tests tests/unit/test_table_hybrid_retrieval.py use synthetic tables, not frozen gold.
- [x] Task2 TDD scoped hybrid retrieval: app/rag/hybrid.py exposes HybridRetriever(resources,embedding_service) and find(query,allowed_ids,limit=3,mode='hybrid'). BM25/cosine/RRF/rerank, stable tie-breaks, coverage/diversity and context bound. Fail closed for source mismatch, duplicate resource ids, unauthorized ids or invalid vectors; lexical-only remains explicit ablation.
- [x] Task3 scripts/run_table_hybrid_eval.py: exclusive new run output, hash original baseline/scorer/previous repair result/corpus; offline local BGE, frozen algorithm/version/config saved. Both modes with full20 cases, evidence-unit metrics and original source audits. Conditional one live run at gate above; saved public raw proposals support offline failure diagnosis.
- [x] Task4 one independent review, one RED→GREEN fix pass if necessary, all unit tests and targeted Ruff/compile checks; final Chinese report with retrieval/answer distinction, provenance, cost/usage, limits and next step. Retain ignored task ledger because work is not committed.

Run unit tests with --confcutdir=tests/unit (root conftest truncates PostgreSQL). Follow TDD: observe failing synthetic regressions, implement, observe green. No real model/database in tests. Reuse existing model budget gate and strict make_task; do not alter historical helpers or files.

Completion:15 new regression cases RED→GREEN;673 full unit tests passed with3 existing dependency deprecations. One independent read-only reviewer found no P1/P2 issues. No algorithm adjustment after seeing the v1 metrics. Hybrid evidence12/14@3 and strict answers10/14;3 task errors and1 frozen-anchor evidence failure retained. Result/report saved separately; no business integration or paid rerun.
