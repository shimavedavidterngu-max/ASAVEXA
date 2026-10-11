# The public landing page

Status: VERIFIED IN TEST ENVIRONMENT (frontend tests and a real-browser run with synthetic data). Not yet verified in staging or production.

## What a visitor sees
A signed-out visitor who opens the site (`/` or `#/welcome`) sees the landing page instead of a bare sign-in box.

- **Header:** logo and name, Product, Solutions, How it works, Security, About, and the two actions Sign In and Get Started. On a phone the links collapse into a menu button.
- **Hero:** "Financial Truth. Backed by Evidence." with the supporting message, a Get Started button and an Explore the Platform button. Beside it is a picture of a "proof thread": a figure, its journal, its evidence, and a bank statement shown as missing. The picture is labelled "Example" with "Sample figures, not real data" and contains no numbers.
- **Product:** the eight things that are built and running, each tied to a real page in the app.
- **Solutions:** the eight professional workspaces, and the kinds of organisation the platform is designed for. That list is design intent, not a customer list, and says so.
- **How it works:** six steps from setting up an organisation to a traceable report.
- **Security:** six statements about what the software does today, and a box headed "Where ASAVEXA stands today" that says the platform is tested with synthetic data and is not yet independently audited, penetration-tested, certified or professionally reviewed.
- **About, final call to action, footer.**

## What it never says
No customer logos, testimonials, certifications, performance figures, partnerships or absolute claims ("100% secure"). A test scans all the copy for these.
The privacy policy, terms of use and contact address are shown as "not published yet" / "to be added by the ASAVEXA team". Nothing is invented. When real ones exist, put them in `frontend/src/lib/landing.js` (`FOOTER`).

## How it is wired
- `frontend/src/lib/landing.js`: all the content and the rule for when the page shows (`signedOutScreen`).
- `frontend/src/pages/Landing.js`: draws it.
- `frontend/src/styles/landing.css`: its look (light and dark, desktop, tablet, phone; respects reduced motion).
- `frontend/src/app.js`: shows the page, handles Sign In / Get Started / Back to the home page, and returns to the page on sign-out.

Rules:
- The landing page shows only on `/` and `/welcome`. A signed-out visitor following a deep link (for example `#/accounting`) goes straight to sign-in, so they still arrive where they meant to.
- Sign In opens the sign-in form. Get Started opens the Create account form. The sign-in screen has a "Back to the home page" link.
- Signing out returns to the landing page. A session that expires, or a return from single sign-on, goes to the sign-in screen. A public lookup that happens to return 401 with no session does not skip the landing page.
- A signed-in user who opens `#/welcome` is sent to the dashboard.
- Shared passport links (`#/shared/...`) are untouched and stay public.

## Also fixed in this release
Cards laid side by side (the Financial Analysis tiles, the Professional Workspaces cards) no longer sit lower after the first one. The cause was a stacking margin (`.card + .card`) that also applied inside flex and grid rows; `design-system.css` now cancels it there.

## What is not built yet
From the Enterprise Interface spec: the guided onboarding after sign-up, the new main dashboard layout, the organisation switcher and global search. The "Resources" link in the spec's header is shown as "How it works", because no separate resources content exists yet.

## Tests
`frontend/tests/landing.test.js` (30 tests): when the page shows, the spec headline and buttons, no invented claims or contact details, every capability points at a real route that is in the menu, every control has a handler, the mobile menu, the honesty of the picture, accessibility basics, sign-out and expiry behaviour, and the card fix.
Real-browser run (66 checks): desktop, tablet, phone and 320px widths, dark mode, contrast, keyboard (skip link, focus), reduced motion, the real sign-in and sign-out round trip, deep links, and card alignment.
Screenshots: `docs/images/landing/`.
