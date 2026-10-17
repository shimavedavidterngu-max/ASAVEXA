"""Browser journey: the proof behind a statement line (Stage 5). Run via e2e/run_all.py.
A trial balance line opens its own proof (posted entries, evidence, reconciliation) without leaving the page; nothing is computed in the browser."""
from common import *

start_web()
p, b, pg, errs = session()
sign_in(pg, *DARA, "Meridian"); goto(pg, "/reporting")
pg.wait_for_selector("select", timeout=8000)
pg.select_option("select >> nth=1", label="FY2026-M01"); pg.click("button:has-text('Generate')"); pg.wait_for_selector(".data-table", timeout=8000)

check("amounts are shown exactly, with grouping", "1,075,000.00" in pg.inner_text(".data-table"), pg.inner_text(".data-table")[:300])
marks = pg.locator(".data-table button.pm")
check("every line has a proof mark", marks.count() >= 2, marks.count())
check("before it is opened, a mark says the proof is not checked (and claims nothing)", all("Proof not checked" in (m.get_attribute("aria-label") or "") for m in marks.all()), [m.get_attribute("aria-label") for m in marks.all()])
check("the page does not load any line's proof until asked", pg.locator("#lp-x").count() == 0 and pg.locator(".pr").count() == 0)

cash = pg.locator("tr", has_text="Cash at bank").first
cash_mark = cash.locator("button.pm")
cash_mark.click(); pg.wait_for_selector(".pr", timeout=8000)
check("opening the mark did not leave the Trial Balance (it is not the row's drill-down)", pg.locator("h3:has-text('Show Me the Number')").count() == 0)
rail = pg.locator(".pr")
check("the rail names the account", "1000 — Cash at bank" in rail.inner_text(), rail.inner_text()[:200])
steps = {s.get_attribute("data-stage"): s.inner_text() for s in rail.locator(".pr-step").all()}
check("posted entries are counted from the server's list", "Posted entries" in steps.get("source", "") and "2 posted entries" in steps.get("source", ""), steps)
check("evidence says how many entries are missing it", "1 of 2 entries missing evidence" in steps.get("evidence", ""), steps)
check("reconciliation is worded from the server's counts", "0 reconciled · 1 outstanding · 1 exception" in steps.get("verification", ""), steps)
check("the rail says it in a sentence", "steps linked" in rail.locator(".pr-summary").inner_text(), rail.locator(".pr-summary").inner_text())
check("the mark now says Proof incomplete, and is expanded", "Proof incomplete" in (cash.locator("button.pm").get_attribute("aria-label") or "") and cash.locator("button.pm").get_attribute("aria-expanded") == "true")
check("keyboard focus moved into the rail", pg.evaluate("document.activeElement && document.activeElement.classList.contains('pr')"), pg.evaluate("document.activeElement && document.activeElement.outerHTML.slice(0,80)"))

pg.keyboard.press("Escape"); pg.wait_for_timeout(400)
check("Escape closes the rail", pg.locator(".pr").count() == 0)
check("and focus goes back to the mark that opened it", pg.evaluate("document.activeElement && document.activeElement.classList.contains('pm')"), pg.evaluate("document.activeElement && document.activeElement.outerHTML.slice(0,80)"))
check("the mark keeps what was found (no second request needed)", "Proof incomplete" in (pg.locator("tr", has_text="Cash at bank").first.locator("button.pm").get_attribute("aria-label") or ""))

# Enter on the mark must not also trigger the row's own drill-down
pg.locator("tr", has_text="Cash at bank").first.locator("button.pm").focus(); pg.keyboard.press("Enter"); pg.wait_for_timeout(1200)
check("Enter on a mark opens the rail only", pg.locator(".pr").count() == 1 and pg.locator("h3:has-text('Show Me the Number')").count() == 0)
pg.click(".pr-close"); pg.wait_for_timeout(400)
check("the Close button works too", pg.locator(".pr").count() == 0)

# An account that is not a bank account has no reconciliation step (not applicable is not a gap)
other = pg.locator("tr", has_text="Revenue").first
if other.count():
    other.locator("button.pm").click(); pg.wait_for_selector(".pr", timeout=8000)
    check("a non-bank account shows no reconciliation step", pg.locator(".pr .pr-step[data-stage=verification]").count() == 0, pg.locator(".pr").inner_text()[:300])
    pg.keyboard.press("Escape"); pg.wait_for_timeout(300)

# The old behaviour is intact: clicking the row itself still goes to the trace for that account
pg.locator("tr", has_text="Cash at bank").first.locator("td").first.click(); pg.wait_for_timeout(2000)
check("clicking the row itself still opens the trace", pg.locator("h3:has-text('Show Me the Number')").count() == 1)

check("no browser errors", not errs, errs[:3])
finish(p, b)
