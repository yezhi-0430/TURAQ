# 项目冗余清理 Implementation Plan

> Execute inline using superpowers:executing-plans, one final independent read-only review. User explicitly requests removal of unnecessary files/tests/code. Preserve current product behavior; no commits, pushes, deployment, live model requests or business database/index changes.

**Goal:** Remove demonstrably unused prototypes, legacy duplicate analysis and non-asserting manual test scripts while retaining current behavior and reproducible research evidence.

**Architecture:** Current frontend is frontend/index.html with native modules; no entry references frontend/src. Current analysis uses app.analysis.quality and its rules, with only FinancialReportParser.extract_financial_indicators from the old class. Legacy RiskAnalyzer and EastmoneyRealCrawler have no runtime consumers beyond obsolete scripts/package re-export. Frozen evaluation inputs/results and educational CLI examples remain intact.

**Tech Stack:** PowerShell native file operations, Python AST/reference checks, pytest isolated from PostgreSQL, Node tests, Vite/npm.

## Constraints

- Preserve .env, .venv, business data, Chroma stores, original report sources and all frozen evaluations; never print secrets.
- Preserve existing uncommitted changes and unrelated personal/resume artifacts. Copy affected original files into ignored .local-backups/cleanup-2026-10-25 before deletion/edit, including hash manifest.
- Recursive removal must validate absolute paths inside this workspace, reject reparse points, use PowerShell Remove-Item -LiteralPath only.
- Do not remove executable assertion tests simply to reduce test count; remove only five obsolete print/manual scripts outside tests/ and embedded obsolete demos.
- No feature additions or behavior changes; no new tests that mirror deletion. Compare pre/post retained AST and run existing relevant coverage.

## Task1: Baseline and concrete inventory

- [x] Confirm actual imports/entry points for frontend/src, standalone.html, RiskAnalyzer, EastmoneyRealCrawler and five scripts/test_*.py. Retain learning demos and all tests/.
- [x] Save original files and fingerprints, pre-cleanup git status and directory counts in ignored cleanup backup.
- [x] Run unit baseline: `.venv/Scripts/python.exe -X utf8 -m pytest tests/unit --confcutdir=tests/unit -o addopts='' -q` →725 passed. Run current frontend tests/build to establish behavior.

## Task2: Remove unused code and dependencies

- [x] Delete frontend/src (13 files), frontend/standalone.html, unused frontend/analysis.js and five legacy scripts: test_complete_analysis.py, test_rag.py, test_rag_usefulness.py, test_crawler.py, test_stock_api.py. No active references remain.
- [x] Delete app/analysis/risk_analyzer.py and app/rag/crawlers/eastmoney_real_crawler.py. Remove obsolete RiskAnalyzer re-export from app/analysis/__init__.py.
- [x] In app/analysis/pdf_parser.py retain extract_financial_indicators body/signature exactly; remove unused constructor keywords, old unbounded PDF extraction, unused ratios and parse_report, embedded print test, obsolete imports. Financial rules/ratio calculations in quality.py stay byte-identical.
- [x] Remove react, react-dom and @vitejs/plugin-react from frontend dependencies and Vite plugin list; update package-lock through npm uninstall, scripts unchanged. Keep Vite/API proxy/workspace bundler.
- [x] Replace retired standalone deployment advice with current index/Vite build instructions, update inaccurate README analysis description and explain frontend structure. Preserve historical reports verbatim.

## Task3: Verification and generated cache cleanup

- [x] Run existing unit suite, isolated auth/limit/deadline checks and Node frontend tests; Vite build plus built asset validation. Expect no retained tests removed and same725 unit baseline.
- [x] Check retained parser method AST equality, current frontend entry references, frozen method/corpus/result fingerprints, secrets/config hashes and no dangling live imports.
- [x] Review cleanup diff with one independent fresh-context reviewer; resolve material issues using reproduction then minimal fix, no repeated review loop.
- [x] Clear verified cache files under .pytest_cache, .ruff_cache and app/scripts/tests/learning __pycache__; empty directories remain because both bulk and empty-directory removals were policy-rejected. Retain runnable build output and dependency environments.
- [x] Save deletion/dependency counts and real check results to docs/repository-cleanup-2026-10-25.md, mark checklist complete.
