# Stage 4 — Shared experiences (landing, sign-in, recovery, home accent)

Status: **VERIFIED IN TEST ENVIRONMENT, NOT DEPLOYED.** Not committed by me; the user commits and pushes.

## What changed
- **Landing:** the hero proof thread is now interactive. Each step is a real button (aria-pressed); choosing one shows what a real record holds there, in a polite live region. Linked steps say "linked" and the missing one says "missing", plus shape. Still labelled "Example, sample figures, not real data", and contains no numbers. Choice is held in app state (`landingBead`).
- **Sign-in, sign-up, second step (MFA) and password recovery:** new two-panel layout (ledger-paper panel with three statements the product backs, beside the form). Panel hidden on screens 900px and narrower. Fixed-width cards removed. **No sign-in logic, ids, labels or handlers were changed.**
- **Home:** sector name shown as an eyebrow, and the shell carries `data-sector` so the accent pair from Stage 3 applies (active menu item, attention list). The sector comes only from the organisation's saved type (`lib/sector.js`); unknown or unconfigured gives nothing. Colour is a cue only; the label is in words.
- A pre-existing menu mapping gap was caught by a new test against the real server catalogue (INDIVIDUAL and BUSINESS types) and fixed.

## Measured (this sandbox)
- Frontend suite: 1396 of 1396 pass (landing 35, auth panel 4, sector tests added).
- Headless Chromium, 320/768/1024/1440 px, light and dark: landing 64/64, sign-in and recovery 56/56 (no horizontal overflow, text contrast at least 4.5:1, keyboard select keeps focus, no console errors).
- End-to-end journeys against the real backend: see final count in the delivery message.

## Not changed / not checked
- Onboarding steps and navigation grouping were left as they are: onboarding by organisation type and menu filtering by the saved type already exist and are tested. The home card grid and "Finance at a glance" are unchanged and are Stage 5 candidates.
- Real devices, screen readers, other browsers, performance, and the live site.
