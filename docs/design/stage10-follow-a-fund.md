# Stage 10: "Follow a fund" for faith-based organisations (donor names never shown)

Status: built and tested in the test environment. **Not deployed; CI and Render results not yet confirmed.**

## Scope, honestly
There is no church-specific backend. A congregation records a designated fund in Public Finance (the grant record: amount, designated purpose, gifts received, spending a second person approves, evidence). When the organisation's saved type is Faith-based, the "Follow a grant" tab becomes **"Follow a fund"**: fund wording ("set aside for this designated fund", "Gifts received", "Purpose as entered") and the **donor field is never shown** on that view, including in the picker.

## What is and is not protected (updated in Stage 11)
- Protected in the browser, for faith-based organisations: the Follow a fund view, the **Grants list** (no Donor column), the **grant's own page**, and the new-fund form (which asks for a general source such as "Congregation", never a person's name). Tests search the whole page for the donor's name, at laptop and phone width.
- NOT changed: the server still stores and returns the donor field (the journey checks this), so the name is in the network response and in the **server's CSV export of an approved report**. The masking is a display rule, not removal of data. Enter a general description as the source.
- Entries typed into the spending description are the person's own text and are not filtered.

## Honesty rules
Same as Stage 9: server figures only, no arithmetic in the browser, waiting is not spent, "Not checked" never zero, read view only, and it does not judge whether a fund is spent as intended.

## Files
`frontend/src/lib/grantTrace.js` (mode "fund"), `frontend/src/pages/Pubfin.js` (`sector` prop), `frontend/src/app.js` (passes the sector), `frontend/tests/granttrace.test.js` (+10, 25 in file), `e2e/journey_pubfin_fund.py` (18 checks; configures the organisation as a congregation through the real entity-configuration route).

## Not checked
Real devices, screen readers, other browsers, performance, the live site, and the other pages that still show the donor.
