# The signed-in home page and the new menu

Status: VERIFIED IN TEST ENVIRONMENT (frontend tests and a real-browser run with synthetic data). Not yet verified in staging or production.

## What a signed-in person sees
- **Welcome line:** their name (from their email), the organisation's name and their role.
- **Finish setting up:** appears only while the organisation is missing something real (no chart of accounts, no open period, no evidence, no second person). Each step has a Go button to the page where it is done. A step that could not be checked says so and is never counted as done or missing.
- **What needs attention:** urgent and watch items taken from each workspace's own overview, urgent first, each a link to the page it concerns. If a source could not be read it is named ("This list may be incomplete") with a Try again button. If the role has nothing to read, it says so instead of claiming all is clear.
- **ASAVEXA AI card:** opens the docked assistant. Hidden with an explanation for roles that cannot question the ledger.
- **Your workspaces:** one card per workspace the role may open, with the true status word from the workspace catalogue and an Open button. Workspaces the role cannot open are tucked behind one link and shown as "Not available to your role" with no Open button. If the catalogue cannot load, no status is shown and the page says why.
- **Quick actions:** up to five, only those the role may do.
- **Finance at a glance:** the existing dashboard cards, unchanged.

## The frame around every page
- **Grouped menu** (replaces the 28-item list): Home, Books and evidence, Professional workspaces, Passport and network, Data and administration, Account and help. The group holding the current page opens by itself; the person can open and close any group. Groups with nothing the role may see disappear.
- **Search:** finds pages by name or by what people call them ("members" finds Administration). It can only ever return pages already in that person's menu. Arrow keys, Enter and Escape work.
- **Breadcrumbs:** Home > group > page (> detail).
- **Organisation switcher:** lists the person's organisations by name. Switching asks the server (which may refuse, for example if the organisation requires two-step sign-in; the refusal is shown) and then reloads the page, so nothing from the previous organisation can remain in memory. "All organisations / create a new one" returns to the picker.
- **Account menu:** email, role, Security, Connection and self-test, Sign out. Signing out also reloads the page.
- **Phone:** the menu becomes a drawer opened by a button; choosing a page, tapping outside or pressing Escape closes it. Menus and search close on any page change.

## Rules
- Role checks only decide what is offered. The server decides what is allowed.
- Nothing on the page is invented: no counts, trends or statuses other than those returned by the server.
- Where a control cannot act (a workspace the role cannot open) it is shown as unavailable, not as a working button.

## Files
`frontend/src/lib/home.js` (logic), `components/Shell.js` (menu, top bar), `pages/Home.js` (page), `styles/home.css`, and `app.js` (wiring). `pages/Dashboard.js` gained a `bare` option so its cards can sit under the new page.

## Also fixed
- Secondary buttons and links were dark on dark in dark mode; now readable.
- A focus/render loop on the search box (found by the browser run) is guarded and has a test.

## Tests
`frontend/tests/home.test.js` (56 tests). Real-browser run (67 checks): owner, finance officer, donor and auditor; desktop, tablet, phone and 320 px; dark mode; keyboard; search; switching organisation and checking that nothing from the first remains; sign-out; no page errors.

## Not built yet
Sign-up onboarding (guided organisation set-up, joining by invitation) is Stage 3. The "Setup" checklist above is the first part of it.
