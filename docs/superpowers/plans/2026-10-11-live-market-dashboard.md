# Live Market Dashboard Implementation Plan

Goal: Complete approved real-quote dashboard in frontend/index.html.
Architecture: FastAPI market router, isolated Tencent quote/minute adapter with bounded cache, standalone frontend module and CSS. No added Python runtime dependencies.

- [x] Tests first: symbols/index distinction, decimal fields, invalid records, timestamps, cache and concurrent coalescing, stale fallback, minute parsing.
- [x] Implement app/market.py and app/market_api.py; register router. Stock list reads existing watchlist items without mutations.
- [x] Implement frontend/market.js and market.css; connect dashboard lifecycle to existing navigation. True snapshot cards, stock table, minute SVG plot, manual refresh, polling and stale/error labels.
- [x] Run focused and existing unit checks, live read-only API probe, JavaScript syntax and lifecycle checks.

Source probe: qt.gtimg.cn and web.ifzq.gtimg.cn both returned HTTP 200. Quotes and minute series carry 2026-10-09 source dates. No paid model calls. Existing unrelated changes preserved. Browser file:// navigation was previously blocked; do not bypass that block. Record visual verification limitation if not available.

Review: fixed partial-response cache loss, per-symbol negative caching, and invalid minute number fallback after reproducing all three in tests. Frontend mock checks cover lazy loading, polling, hidden/exit pause, stale failure, auto-off and invalid input. No visual browser verification; prior file policy block respected.
