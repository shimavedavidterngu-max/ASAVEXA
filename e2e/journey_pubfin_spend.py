"""Browser journey: Public Finance, "Where the money went" (Stage 8). Run via e2e/run_all.py.
Two budgets are built through the real Public Finance service by different people, then read in the browser (which only reads)."""
from common import *

M = "Meridian"
SHOTS = "/tmp/claude-0/-home-claude/60ab6487-5258-5631-bac9-a1da502d1394/scratchpad/shots/"
def P(m, path, who, body=None): return api(m, "/pubfin" + path, who, M, body)
def ok(r, what):
    if isinstance(r, dict) and "body" in r and r.get("status") in (400, 403, 404, 409, 500): raise SystemExit(f"seed failed at {what}: {r}")
    return r
acc = {x["code"]: x["id"] for x in api("GET", "/accounts", DARA, M)}
def budget(name, rent, sales):
    b = ok(P("POST", "/budgets", AISHA, {"name": name, "start": "2026-01-01", "end": "2026-12-31", "currency": "NGN", "lines": [{"account_id": acc["5000"], "amount": rent}, {"account_id": acc["4000"], "amount": sales}]}), "budget")
    ok(P("POST", f"/budgets/{b['id']}/submit", AISHA), "submit"); ok(P("POST", f"/budgets/{b['id']}/approve", KWAME, {"note": ""}), "approve"); return b
tight = budget("Tight budget", "10000.00", "50000.00")       # the posted rent is far above this: over budget
term = budget("Term budget", "500000.00", "800000.00")
c1 = ok(P("POST", "/commitments", AISHA, {"budget_id": term["id"], "account_id": acc["5000"], "vendor": "Hall Landlord", "description": "Hall hire", "amount": "1500.00", "date": "2026-03-01", "evidence_ids": []}), "commitment 1")
c2 = ok(P("POST", "/commitments", AISHA, {"budget_id": term["id"], "account_id": acc["5000"], "vendor": "Stationery Ltd", "description": "Paper", "amount": "2500.00", "date": "2026-03-02", "evidence_ids": []}), "commitment 2")
ok(P("POST", f"/commitments/{c2['id']}/settle", AISHA, {"settled_amount": "2500.00", "note": "Journal J-100"}), "settle")
draft = ok(P("POST", "/budgets", AISHA, {"name": "Draft only", "start": "2026-01-01", "end": "2026-12-31", "currency": "NGN", "lines": [{"account_id": acc["5000"], "amount": "1.00"}]}), "draft")

def steps(pg): return {s.get_attribute("data-stage"): s.inner_text() for s in pg.locator("#pf-spend-rail .pr-step").all()}
def shape(pg, st): return pg.locator(f"#pf-spend-rail .pr-step[data-stage={st}] .pr-bead").get_attribute("class")

start_web()
p, b, pg, errs = session()
sign_in(pg, *AISHA, "Meridian"); goto(pg, "/pubfin")
pg.wait_for_selector("#pf-tab-spend", timeout=8000)
check("the workspace has a Where the money went tab", pg.locator("#pf-tab-spend").count() == 1)
pg.click("#pf-tab-spend"); pg.wait_for_selector("#pf-spend-ledger", timeout=8000)
opts = pg.locator("#pf-spend-budget option").all_inner_texts()
check("only approved budgets can be chosen (the draft is not offered)", len(opts) == 2 and not any("Draft only" in o for o in opts), opts)
check("the newest approved budget is shown first", "B-" in pg.inner_text("#pf-spend-title") and "Term budget" in pg.inner_text("#pf-spend-title"), pg.inner_text("#pf-spend-title"))
sentence = pg.inner_text("#pf-spend-sentence")
check("the plain sentence uses the server's figures exactly", sentence == "Of the 500,000.00 NGN approved for 5000 Rent, 200,000.00 NGN has been spent (posted to the ledger), 1,500.00 NGN is promised in open commitments, and 298,500.00 NGN is still available.", sentence)
t = steps(pg)
check("the rail has four steps in order", list(t.keys()) == ["authorised", "committed", "spent", "evidence"], list(t.keys()))
check("authorised: approved by a second person", "Approved" in t["authorised"] and "500,000.00" in t["authorised"] and "second person" in t["authorised"], t["authorised"])
check("promised: one open, one settled, listed with references", "1 still open" in t["committed"] and "Hall Landlord" in t["committed"] and "Stationery Ltd" in t["committed"], t["committed"])
check("spent: posted, and ASAVEXA says it did not pay", "Posted" in t["spent"] and "200,000.00" in t["spent"] and "did not make any payment" in t["spent"], t["spent"])
check("evidence: not linked, said in words with the references", "Not linked yet" in t["evidence"] and "2 of 2" in t["evidence"], t["evidence"])
check("a missing step is drawn hollow-dashed (shape, not only colour)", "is-missing" in shape(pg, "evidence") and pg.locator("#pf-spend-rail .pr-step[data-stage=evidence] .pr-dash").count() == 1)
check("the in-progress step has its own shape", "is-pending" in shape(pg, "committed"), shape(pg, "committed"))
check("the commitments list says no evidence is linked", pg.inner_text("#pf-spend-commitments").count("No evidence linked") == 2, pg.inner_text("#pf-spend-commitments"))
check("the income table is shown separately", "4000 Sales" in pg.inner_text("#pf-spend-income") and "800,000.00" in pg.inner_text("#pf-spend-income"), pg.inner_text("#pf-spend-income"))
check("the rail says it is not complete", pg.locator("#pf-spend-rail.is-complete").count() == 0 and "of 4 steps linked" in pg.inner_text("#pf-spend-rail .pr-summary"), pg.inner_text("#pf-spend-rail .pr-summary"))

# ---- the tight budget: over budget in words ----
pg.select_option("#pf-spend-budget", tight["id"]); pg.wait_for_selector("#pf-spend-lines", timeout=8000); pg.wait_for_timeout(600)
check("over budget is said in a word, not only colour", "over budget" in pg.inner_text("#pf-spend-lines").lower(), pg.inner_text("#pf-spend-lines"))
s2 = pg.inner_text("#pf-spend-sentence")
check("the sentence says how much more was used, without a minus sign", "190,000.00 NGN more has been spent or promised than was approved" in s2 and "-" not in s2.split("approved for")[1][:30], s2)
t = steps(pg)
check("nothing promised is said plainly on the tight budget", "Nothing promised yet" in t["committed"], t["committed"])
check("with nothing promised there is nothing to evidence", "Nothing to evidence yet" in t["evidence"], t["evidence"])

# ---- a read view ----
check("the page offers no settle, approve, cancel or pay buttons in the ledger", pg.locator("#pf-spend-ledger button").count() == 0)

# ---- the same figures the server gives ----
ex = P("GET", f"/budgets/{term['id']}", KWAME)["execution"]["rows"]
rent = [r for r in ex if r["code"] == "5000"][0]
check("the server's own execution matches the page", rent["available"] == "298500.00" and rent["actual"] == "200000.00", rent)

# ---- another company sees none of it ----
other = api("GET", f"/pubfin/budgets/{term['id']}", OTHER, "Other")
check("another company cannot read the budget", isinstance(other, dict) and other.get("status") in (403, 404), other)

# ---- phone width ----
ctx = b.new_context(viewport={"width": 390, "height": 1800}); pg2 = ctx.new_page(); pg2.route("https://asavexa.onrender.com/**", handle)
sign_in(pg2, *AISHA, "Meridian"); goto(pg2, "/pubfin"); pg2.click("#pf-tab-spend"); pg2.wait_for_selector("#pf-spend-rail"); pg2.wait_for_timeout(500)
check("no sideways overflow at 390px", pg2.evaluate("document.documentElement.scrollWidth") <= 390, pg2.evaluate("document.documentElement.scrollWidth"))
pg2.screenshot(path=SHOTS + "spend-390.png"); pg.screenshot(path=SHOTS + "spend-1300.png")
check("no browser errors", not errs, errs[:3])
finish(p, b)
