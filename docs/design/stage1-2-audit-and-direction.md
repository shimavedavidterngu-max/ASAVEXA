# ASAVEXA design programme: Stage 1 (audit) and Stage 2 (art direction)

Status: **PLAN ONLY. No product code was changed in these stages.** Everything below was read from the repository on 2026-10-17. Nothing here is a claim about the live site.

## Stage 1: What the product was before the redesign

### How the front end is built
- Zero-build vanilla JavaScript (native ES modules), served by nginx / Vercel. 68 page files, 56 logic files in `src/lib`, 10 shared components, 6 stylesheets.
- One 6,132-line `app.js` owns state, routing and wiring. A small virtual-DOM helper (`lib/vdom.js`) draws everything and already supports SVG, so purpose-built charts need no new dependency.
- 74 frontend test files, 1,340 tests passing at the time. 32 browser-journey scripts in `e2e/`.

### What already worked well (kept)
- A real brand seed: navy / teal / gold, Fraunces for display. The landing hero already used ruled ledger paper with a gold margin line and a "proof thread".
- Honest copy: sample data labelled "Example"; missing links shown as missing.
- A central traceability component (`EvidenceChain`) that never fabricates a relationship.
- Accessibility groundwork: skip link, `:focus-visible`, reduced-motion handling, ARIA on menus, a dark theme.
- A role-aware home whose "needs attention" list says which source failed instead of showing a reassuring zero.

### What was weak
1. The fonts were never loaded (no `@font-face`), so the type identity did not exist.
2. Workspaces all looked the same (identical tab rows, the same `.card`, mostly inline styles).
3. The home page was partly the generic pattern: welcome, attention list, AI card, a grid of workspace cards, metric cards.
4. Navigation was one flat group of about 35 workspaces; no notion of "my sector".
5. Login was a 360px card on a navy field with inline styles.
6. The signature trace existed but was buried across separate screens.
7. No numeric typography system: money columns were not guaranteed to align.
8. Thin responsive breakpoints.

### Not known at the time
Real-device rendering, contrast ratios, screen-reader behaviour, performance. None were measured then, so none were reported.

## Stage 2: Three genuinely different directions

- **A. "Ledger Paper"** (editorial, document-first): calm paper tones like a well-set financial statement; every figure has a numbered margin mark that opens its provenance beside it.
- **B. "Observatory"** (instrument panel): dark by default, three persistent panes, command palette first, density first.
- **C. "Proof Spine"** (lifecycle-first): the chain is the navigation; a vertical spine shows a record's journey from source to verification.

### Evaluation (my judgement, 1 weak to 5 strong; not a measured result)
| Criterion | A | B | C |
|---|---|---|---|
| Professional credibility | 5 | 4 | 4 |
| Fit across sectors | 4 | 2 | 4 |
| Memorability | 4 | 4 | 5 |
| Usability for non-technical staff | 4 | 3 | 3 |
| Accessibility | 5 | 3 | 4 |
| Density where needed | 4 | 5 | 3 |
| Feasibility, low regression risk | 5 | 3 | 3 |
| **Total (of 35)** | **31** | **24** | **26** |

### Decision
**Direction A, "Ledger Paper"**, with Direction C's best idea as one component, the **Proof Rail**: a compact vertical thread, opened from any figure's margin mark, showing source, evidence, review, decision, authorised action and independent verification for that record, with hollow beads for missing steps.

### Sector signatures (each built only when its stage starts)
| Sector | Signature element |
|---|---|
| Accounting | Balance, contributing entries, evidence, adjustments, resolution history |
| Procurement | Request, approval, supplier, contract, delivery, invoice (three-way match), payment, verification |
| Health administration | Authorised, purchased, delivered, unresolved by department; no patient data |
| Schools | Budget-to-expenditure by department in plain language |
| Churches | Designated fund, authorised purpose, spending, evidence; donor names never shown |
| NGOs | Funding, restriction, spend, activity, output, outcome evidence |

## Staged plan
| Stage | Scope |
|---|---|
| 3 | Visual system: tokens, aligned figures, Proof Rail and margin mark, style guide |
| 4 | Shared experiences: landing, sign-in and recovery, role-aware home with sector accent |
| 5 | Accounting ledger and reconciliation trace |
| 6 | Procurement Trace as the first specialist workspace |
| 7+ | One sector per stage, starting with Health administration |

## What will not be done
No fake customers, logos, testimonials, certifications or invented figures; illustrative data is always labelled. No new dependency without a stated benefit. No change to authentication or tenant-isolation logic.
