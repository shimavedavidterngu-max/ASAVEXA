# Stage 15: "Needs attention" opens the proof

The Overview listed problems (a line spent beyond its budget, a grant past its end date, spending beyond cash received) as plain text. Each now has a button that opens the proof view for that item.

- Overspent budget line: **Where the money went**, on that budget, with that line selected.
- Grant past its end date, and grant with approved spending beyond cash received: **Follow a grant** (or **Follow a fund**), on that grant.
- Backend (additive only): the overview now returns `budget_id` and `account_id` on overspent lines and `id` on the two grant lists. Nothing was removed or renamed.
- If a server does not send the ids, the text is shown without a button (never a broken one).
- The sentences and figures are unchanged; the server's own numbers are restated.

Tests: 2 Python (`OverviewLinks`), 4 frontend (`overviewlinks.test.js`), browser `e2e/journey_pubfin_attention.py` (10 checks, fresh server, 390px checked and viewed).
