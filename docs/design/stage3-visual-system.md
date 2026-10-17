

---

## Stage 3 — Visual system (built and tested; NOT committed, NOT deployed)

Status: **VERIFIED IN TEST ENVIRONMENT, NOT DEPLOYED.** No existing page was redesigned; Stage 3 only adds a stylesheet, components and a style-guide fixture.

### What was added
- `frontend/src/styles/ledger.css`: tokens, sector accent pairs (`data-sector`), aligned figures, margin mark, Proof Rail, statement table, page frame, reduced-motion and forced-colours rules. Linked from `index.html`.
- `src/components/Figure.js` (figure + numbered margin mark) and `ProofRail.js` (source, evidence, review, decision, authorised action, independent verification). `null` reads "Not linked yet"; an omitted step reads "Not checked". State is a different shape plus words, never colour alone.
- `src/lib/figures.js`: exact decimal-string money formatting (no floats, no rounding, mixed currencies refused). `src/lib/contrast.js`: WCAG contrast maths.
- Fraunces 600 self-hosted with its OFL licence. **Inter and IBM Plex Mono were NOT bundled** (font downloads were blocked here); they stay as system fonts.
- One fix to existing `design-system.css`: `.btn-secondary` text was unreadable on the dark theme.
- Style guide fixture (illustrative data, labelled): `frontend/tests/fixtures/styleguide.html`.

### Measured results (this sandbox)
- New ledger unit tests: 41/41. Full frontend suite: 1381/1381.
- Headless Chromium: 54/54 checks (320/768/1024/1440 px, light and dark, font loaded, keyboard open/close with focus return, tap targets at least 24px, rendered text contrast at least 4.5:1, no console errors, reduced-motion, forced-colours, no horizontal overflow).
- Accent text on paper: at least 5.68:1 light, at least 7.92:1 dark.
- `release_check.py`: 10/10. Python suite: 2331 run, OK, 8 PostgreSQL skips.

### Not checked
Real devices, screen readers, other browsers, performance, and the live site.
