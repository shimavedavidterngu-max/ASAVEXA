# ASAVEXA — Frontend Runtime Verification & Architecture

Companion to `docs/runtime-verification.md`, `docs/postgresql-runtime-verification.md`,
and `docs/security-architecture.md`. Same honesty rule: nothing here
claims real browser/FastAPI integration occurred, because it hasn't —
this environment has no network access to the npm registry (confirmed
directly: `npm install react` returns `403 Forbidden`), the same
constraint that shaped every backend phase.

## Framework decision — and why it isn't React/Vue/etc.

Per this phase's own instruction ("do not assume React/Vite/Next.js
without inspecting the repository... choose the smallest
production-appropriate architecture"): Node v22.22.2 and npm 10.9.7
are installed, but `npm install <anything>` fails — the registry is
unreachable from this sandbox. A bundler-based framework was therefore
not viable to build *or test* here.

**Chosen architecture: vanilla JavaScript, native ES modules, zero
build step, zero npm dependencies.** This mirrors the backend's own
governing discipline (stdlib-only, fully testable without installable
packages) applied to the frontend:

- `frontend/src/lib/vdom.js` — a ~60-line hyperscript (`h()`) +
  `mount()` utility. `h()` returns a plain, inert JS object (a
  "vnode") that never touches `document` — this is the single design
  decision that makes component *logic* unit-testable in plain Node
  (no DOM implementation is available here either — `jsdom` also needs
  `npm install`). Only `mount()` touches real `document` APIs, and it
  is small enough to review directly; it cannot be unit-tested in this
  environment and is explicitly marked "pending real browser" below.
- No JSX, no virtual-DOM diffing — `mount()` does a full
  `replaceChildren()` + rebuild on every render. Simpler and slower
  than a diffing framework, appropriate for this application's actual
  interaction rate (form submissions and page navigations, not
  high-frequency updates), and — critically — buildable and testable
  with zero external tooling.
- Runs directly in any modern browser via `<script type="module">` —
  no webpack/Vite/esbuild step, ever, in development or production.
  `index.html` loads `src/app.js` as a native ES module.

If real npm access becomes available later, this can be incrementally
adopted into a framework (the vnode shape is a deliberately React-like
`{tag, props, children}`, making a later migration mechanical rather
than a rewrite) — but that migration is out of scope here and not
started, since it isn't needed to deliver a working, tested UI now.

## A. Frontend architecture

```
frontend/
├── index.html                  entry point, loads app.js as a module
├── src/
│   ├── app.js                   orchestration: auth check -> org
│   │                             selection -> shell -> routed page
│   │                             (browser-only, not unit-tested — see
│   │                             "Verified vs pending" below)
│   ├── api/client.js             ApiClient — the ONLY fetch() call site
│   ├── state/auth-store.js       AuthStore — token/user/org/role state
│   ├── lib/
│   │   ├── vdom.js                h()/mount() — see above
│   │   ├── router.js              hash-based router; matchRoute() is
│   │   │                          pure and tested, start()/navigate()
│   │   │                          touch window and are not
│   │   └── permissions.js         can() + the mirrored ROLE_PERMISSIONS
│   │                              matrix (copied from the real backend
│   │                              registry, not derived or guessed)
│   ├── components/
│   │   ├── StatusBadge.js         backend-enum -> badge tone mapping
│   │   ├── PermissionGate.js      the one place UI hides an action
│   │   └── EvidenceChain.js       the Section 11 traceability primitive
│   ├── pages/
│   │   ├── Login.js               + OrganisationPicker
│   │   ├── Dashboard.js
│   │   └── AuditWorkspace.js      + buildChainLinks()
│   └── styles/design-system.css
└── tests/                        node:test files, one per module above
```

Every page/component file exports a **pure function**: `Component(props) -> vnode`.
No component calls `fetch` itself — `app.js` is the only place that
calls `ApiClient` methods and passes the results down as props. This
is what makes 85 of the 85 frontend tests genuine, executable
verification rather than mocked-DOM theater.

## B. Navigation architecture

Hash-based routing (`#/path`), matched against:

| Route | Page | Built this pass? |
|---|---|---|
| `/` | Dashboard | **Yes** |
| `/audit` | Audit Workspace | **Yes** |
| `/accounting` | Accounting | No — "Not yet built" state |
| `/evidence` | Evidence Vault | No — "Not yet built" state |
| `/reconciliation` | Reconciliation Workspace | No — "Not yet built" state |
| `/reporting` | Reporting | No — "Not yet built" state |
| `/period-close` | Period Close Workspace | No — "Not yet built" state |
| `/compliance` | Controls & Compliance | No — "Not yet built" state |
| `/admin` | Organization/User Administration | No — "Not yet built" state |

Every route is permission-filtered in the sidebar (`app.js`'s
`NAV_ITEMS`) via `allowed(role, permission)` — an item the current
role can't use never appears, matching Section 2's "only expose areas
the authenticated user's permissions allow." A route with no page
built yet shows an honest, explicit message (Section 17: never a blank
screen) naming exactly what's missing, rather than a fabricated page.

## C. Component architecture

Three reusable primitives, each with dedicated tests:

- **`StatusBadge`** — maps every real backend status enum value
  (`ControlResult`, `FindingStatus`, `RemediationStatus`,
  `JournalStatus`, `PeriodStatus`/`PeriodCloseStatus`,
  `ReconciliationStatus`/`BankTransactionStatus`, `EvidenceStatus`) to
  one of five visual tones. An unrecognized value falls back to
  neutral rather than crashing.
- **`PermissionGate`** — Section 15's `can(permission)` made concrete:
  wraps a privileged action, rendering it only if the current role
  holds the permission. Explicitly documented (and tested) as UX only
  — see "Permission-aware UI is UX, not security" below.
- **`EvidenceChain`** — Section 11's core requirement. Renders exactly
  the eight documented stages (Transaction → Evidence → Reconciliation
  → Control → Finding → Remediation → Verification → Audit Event) in
  order, every time, regardless of how much data is available. A stage
  with no data renders the literal text "No linked record" — proven by
  a dedicated test that an empty `links` array still produces all
  eight stages, each explicitly marked missing, never silently
  omitted and never fabricated.

## D. API client

`ApiClient` (`src/api/client.js`) is the single `fetch()` call site in
the entire frontend. Every method's path was copied directly from the
real router source (`src/asavexa/api/routers/*.py`) during this pass —
not invented from the product brief's description of what *should*
exist. Handles: base URL (`/api`, intended to be reverse-proxied to
the real FastAPI app), Bearer token injection, JSON (de)serialization,
and a single `ApiError`/`NetworkError` distinction with a `.kind`
classifier (`unauthenticated`/`unauthorized`/`not_found`/`conflict`/
`validation`/`server_error`/`bad_request`) mirroring the backend's own
status-code buckets (`docs/security-architecture.md`'s error-behavior
section) rather than re-deriving them independently.

Does not retry mutating requests (a retried `POST` that actually
succeeded server-side but lost its response could double-post a
journal). Does not implement any financial calculation — every number
displayed is what the backend returned, formatted for presentation
only (`Dashboard.formatMoney`, tested to prove it never invents a
figure for missing data — returns "—", not "0.00").

## E. Authentication

`AuthStore` mirrors the real backend session model exactly
(`docs/security-architecture.md`): a bearer token plus the currently
selected organisation and role, held in `sessionStorage` (cleared when
the tab closes — deliberately not `localStorage`, and never a cookie,
since this app has no CSRF-protection layer built for cookie auth).
Login flow: `POST /auth/register` (if registering) → `POST /auth/login`
→ token stored → if the user belongs to zero or multiple
organisations, `OrganisationPicker` lists exactly what
`GET /organisations/mine` returned (never fabricates an org) →
`POST /auth/select-organisation` → the resulting `role` (resolved
server-side from the real membership, never client-chosen) is stored
alongside the org id. A `401` from any request clears the session and
returns to the login screen (`ApiClient`'s `onUnauthenticated` hook →
`AuthStore.clear()`).

## F. Permission-aware UI

`lib/permissions.js` mirrors `identity/domain/permissions.py`'s
`ROLE_PERMISSIONS` field-for-field — verified by dedicated tests
reproducing three of the real backend's own documented facts:
`ACCOUNTANT` can remediate but not verify a finding; `APPROVER` can
verify but neither manage nor remediate one; `ADMINISTRATOR` can
manage findings but can do neither of the other two. These exact
three-way splits are the maker-checker separation Phase 4's security
audit tested and enforced server-side — this module's tests prove the
*same* facts hold in the frontend's mirrored copy.

**Permission-aware UI is UX, not security** (Section 15, stated
explicitly in three separate places in this codebase: the permission
module's own docstring, `PermissionGate`'s docstring, and here). The
backend independently re-checks every permission on the real request
via `require_permission` and will reject it regardless of what the
frontend decided to render. If the two ever disagree — a stale local
role, a permission this module fails to mirror correctly — the backend
wins, and the UI's job is to surface that rejection cleanly (via
`ApiError.kind === "unauthorized"`), not to have prevented the attempt
by hiding a button. This module has no authority; it has an opinion.

## G. Evidence-first UX

`Dashboard` leads with evidence/control/reconciliation health, not
just financial totals (Section 3) — every metric card is clickable to
its underlying records (`onNavigate`), tested to confirm each click
fires with the correct real route.

## H. Audit Workspace

Built exactly as specified (Section 11): a search box takes a journal
id, and `buildChainLinks()` — a pure, independently tested function —
maps whatever the container actually fetched into the eight-stage
`EvidenceChain`. Nothing is fetched or inferred by the render function
itself; `app.js`'s `handleAuditSearch` performs the real sequence of
API calls (`GET /journals/{id}` → `GET /journals/{id}/audit-trail` →
`GET /evidence/status` → `GET /evidence/{id}` if found) and passes
only what it actually got back. A relationship the container couldn't
resolve is passed as `null` and renders as "No linked record" — proven
by seven dedicated `buildChainLinks` tests covering every
present/absent combination, including the "all inputs empty" case
(all eight stages show missing) and a fully-populated case (all eight
show real data with correct navigation hrefs).

## I. Testing

### Backend tests (unaffected by this phase)
```
PYTHONPATH=src python3 -m unittest discover -s tests -v
Ran 245 tests in 22.1s — OK
```

### Frontend tests (this phase — genuine, executable, zero mocked DOM)
```
node --test frontend/tests/*.test.js
# tests 85
# pass 85
# fail 0
```
Covers: API client request construction + error mapping (12 tests),
permission model parity with the backend (9), vnode construction (5),
auth store lifecycle including simulated page-refresh persistence (8),
StatusBadge + PermissionGate (11), EvidenceChain's never-fabricate
guarantee (7), Dashboard's real-data-only rendering (7), AuditWorkspace
+ buildChainLinks (11), Login + OrganisationPicker (7), router path
matching (6), and more. Every test asserts on the vnode tree `h()`
returns or on plain-object state — never touches a real `document`
API, matching the vdom.js testability boundary above.

### Real API/browser integration — explicitly pending
Not executed, and not claimed to be: no live FastAPI server exists in
this environment (unchanged since Phase 2), so `app.js`'s actual
`fetch()` calls, `AuthStore`'s real `sessionStorage` behavior, and
`mount()`'s real DOM painting have never run against anything real.

## Verified / Pending

**Verified (executed)**:
- Component render logic (vnode structure) for every page/component built
- Permission-mirroring accuracy against the real backend registry
- API client request/error-mapping logic against controlled fetch fixtures
- Auth store state transitions, including persistence-across-reload simulation
- Route-matching logic (pure function, no `window`)
- The `EvidenceChain`/`buildChainLinks` never-fabricate guarantee

**Pending (requires a real browser + real running API)**:
- Actual DOM painting, CSS layout, and visual rendering (`mount()`)
- Actual `fetch()` calls reaching a real FastAPI server
- Real `sessionStorage` behavior in an actual browser tab
- Real keyboard navigation, focus management, and screen-reader behavior
  (accessibility attributes are present in the markup — `aria-label`,
  `role`, `tabindex`, labeled form fields — but never tested against a
  real assistive-technology stack)
- Responsive layout behavior at real viewport sizes (CSS media queries
  are written; never rendered)
- File upload flow (no evidence-upload page was built this pass — see
  below)

## What was NOT built in this pass — stated plainly, not implied away

Six of the nine functional areas named in the product brief have **no
page UI yet**: Accounting (chart of accounts, journal workspace,
reversal, period lock), Evidence Vault (list/upload/detail), full
Reconciliation Workspace, Reporting, Period Close Workspace,
Controls & Compliance (control library, findings list, remediation/
verification flow), and Administration (users, memberships, roles).

This is a real, deliberate scope limitation, not an oversight left
undocumented: `ApiClient` already has complete, tested method coverage
for every one of these areas (all confirmed against the real router
inventory), and the reusable component layer (`StatusBadge`,
`PermissionGate`, `EvidenceChain`, the design system) was built
specifically so those pages are straightforward to add next — but they
were not built in this pass, and navigating to any of their routes
shows an explicit "Not yet built" message rather than a fabricated or
broken page. Accessibility work (Section 22) and responsive testing
(Section 19) exist only where the two built pages already cover them
structurally; no dedicated accessibility audit pass was performed.

## Exact commands for real verification once dependencies are available

```bash
# Frontend tests always work here, no install needed:
node --test frontend/tests/*.test.js

# Real browser verification, once real API access exists (see
# docs/runtime-verification.md for starting the real backend):
cd frontend
python3 -m http.server 5173   # or any static file server — no build
                               # step, so none of the usual
                               # dev-server/bundler tooling is required
# open http://localhost:5173 in a real browser, with the real API
# reachable at the /api prefix app.js's ApiClient expects (configure a
# reverse proxy, or change DEFAULT_BASE_URL in src/api/client.js to
# point directly at the running uvicorn instance's host:port)
```
