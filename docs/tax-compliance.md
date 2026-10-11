# Tax Compliance workspace

Menu: **Tax Compliance** (also reachable from Professional Workspaces). Viewing needs `reporting:read`. Selecting countries, entering and submitting rules, calculating and recording filings need `tax:prepare`. Approving or sending back a rule needs `tax:approve`.

## The one rule that shapes everything
**ASAVEXA contains no tax rates.** There are about 200 countries and territories in the list (reference data: code, name, currency, region), but a country has tax rules only after a person enters them from an official source and a *different* person approves them. This is deliberate: rates and thresholds change, differ by country, state and tax type, and a wrong figure on a filing causes real harm.

## How a country is made usable
1. **Countries tab:** search or filter by region, press *Select* for the countries the organisation operates in, and optionally record its registration number there.
2. **Rules tab:** *Enter a new rule*: country, type of tax, name, flat rate or progressive bands, rounding, the date it starts (and ends), the tax authority, the exact law or notice, and a link to the official source. Optionally add the return schedule (how often, days after period end) so it appears in the calendar. Save as draft, then submit.
3. A second person opens the rule, checks it against the source link, and approves it or sends it back with a reason. The person who prepared or submitted a rule can never approve it (enforced on the server). Approval fingerprints the rule (SHA-256).
4. When the law changes, use *Create a replacement*; the old rule is marked Replaced, never edited. Two rules with the same country, tax type and name cannot overlap in time.

## Calculator
Only in-force rules can be used, and only for dates inside the rule's range. Flat rules work with the tax excluded or included in the amount; band rules apply each slice at its own rate. The result shows the working, the rule version, the source and its fingerprint, is labelled ESTIMATE, and is saved to the audit trail. You can start from posted ledger revenue, expenses or net income for a period; that is accounting profit, not taxable income. Exact decimal arithmetic; rounding is part of the rule.

## Calendar
For selected countries with an in-force rule that has a return schedule, deadlines are worked out as period end + the days in the rule. States: Upcoming, Due soon (14 days), Overdue, Filed. *I filed this* records a reference **you** got from the authority. ASAVEXA does not submit anything to any tax authority.

## Limits (read these)
- Tested with invented rates in the build environment only. Not reviewed by a tax adviser or accountant.
- The quality of a country's rules is the quality of the source and the two people who entered and reviewed it.
- No currency conversion; no returns, e-filing, withholding certificates or treaty logic yet.
- A country with no deadlines in the calendar may simply have no rule loaded.
