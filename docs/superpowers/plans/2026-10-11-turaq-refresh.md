# TURAQ Refresh Implementation Plan

Goal: Upgrade the approved standalone frontend into a polished research workspace.
Architecture: Keep HTML, CSS and JavaScript in frontend/index.html for direct file opening. Use inline SVG icons and no external assets.

- [ ] Replace visual layout: editorial landing, illustrative research card, capability strip, responsive workspace and empty states.
- [ ] Preserve chat API; implement accessible navigation, expandable tool records, safe text rendering, busy/error states and structured object formatting.
- [ ] Verify syntax and browser interaction at desktop and mobile sizes; inspect diff for unrelated edits.

Ruling: User approved design and requested implementation; proceed inline without additional approval. Preserve unrelated existing working-tree changes. Use browser checks for this reversible visual update rather than adding implementation-mirroring tests.

Verification: inline JS syntax passed; HTML nesting, IDs and SVG references passed; mocked DOM/network checks passed for navigation, request payload, assistant history, safe text rendering, tool cards, HTTP failure recovery and reset. git diff --check passed. Browser visual validation blocked by file:// policy; no screenshots or real backend/model requests performed. Implementation tasks complete; desktop/mobile visual verification remains outstanding.
