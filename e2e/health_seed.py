"""Seeds one health centre through the REAL health service, by different people (used by journey_health_trace.py).
Pharmacy goes all the way; Laboratory is part-delivered with an invoice that does not match; Administration has an order still waiting for approval."""
from datetime import date, timedelta

import json as _j
import urllib.request

from common import *

D = lambda n: (date.today() + timedelta(days=n)).isoformat()
ORG = "Meridian"
def H(m, path, who, body=None): return api(m, "/health" + path, who, ORG, body)
def ok(r, what):
    if isinstance(r, dict) and r.get("status") in (400, 401, 403, 404, 409, 500) and "body" in r: raise SystemExit(f"seed failed at {what}: {r}")
    return r


def uid(creds):
    r = urllib.request.Request(BASE + "/auth/login", data=_j.dumps({"email": creds[0], "password": creds[1]}).encode(), headers={"content-type": "application/json"}, method="POST")
    return _j.loads(urllib.request.urlopen(r).read())["user"]["id"]


def seed():
    f = ok(H("POST", "/facilities", TUNDE, {"name": "Meridian Health Centre", "type": "PRIMARY_HEALTH_CENTRE", "ownership": "PRIVATE", "region": "Lagos", "currency": "NGN", "block_overspend": True}), "facility")
    fid = f["id"]
    dept = {}
    for code, name in (("PHARM", "Pharmacy"), ("LAB", "Laboratory"), ("ADM", "Administration")):
        dept[code] = ok(H("POST", f"/facilities/{fid}/departments", TUNDE, {"code": code, "name": name}), "dept " + code)["id"]
    for who in (AISHA, KWAME, DARA): ok(H("PUT", f"/access/{uid(who)}", TUNDE, {"facility_ids": [fid]}), "access")
    b = ok(H("POST", f"/facilities/{fid}/budgets", AISHA, {"name": "Year budget", "period_start": D(-30), "period_end": D(300), "lines": [
        {"dept_id": dept["PHARM"], "category": "MEDICAL_SUPPLIES", "amount": "10000.00"},
        {"dept_id": dept["LAB"], "category": "MEDICAL_SUPPLIES", "amount": "5000.00"},
        {"dept_id": dept["ADM"], "category": "ADMINISTRATION", "amount": "2000.00"}]}), "budget")
    ok(H("POST", f"/budgets/{b['id']}/submit", AISHA), "budget submit"); ok(H("POST", f"/budgets/{b['id']}/approve", KWAME), "budget approve")
    sup = ok(H("POST", f"/facilities/{fid}/suppliers", AISHA, {"name": "MedSupply Ltd"}), "supplier")

    def order(dc, cat, desc, qty, price, approve=True):
        rq = ok(H("POST", f"/facilities/{fid}/requisitions", AISHA, {"dept_id": dept[dc], "category": cat, "justification": "Routine restock", "lines": [{"description": desc, "qty": qty, "unit_price": price}]}), "req")
        ok(H("POST", f"/requisitions/{rq['id']}/submit", AISHA), "req submit"); ok(H("POST", f"/requisitions/{rq['id']}/decide", KWAME, {"ok": True}), "req decide")
        po = ok(H("POST", f"/requisitions/{rq['id']}/po", AISHA, {"supplier_id": sup["id"]}), "po")
        if approve: ok(H("POST", f"/pos/{po['id']}/approve", KWAME, {}), "po approve")
        return rq, po

    rq1, po1 = order("PHARM", "MEDICAL_SUPPLIES", "Gloves boxes", "10", "100.00")
    ok(H("POST", f"/pos/{po1['id']}/receive", AISHA, {"delivery_note": "DN-1001", "lines": [{"line_no": 1, "qty": "10"}]}), "receive 1")
    inv1 = ok(H("POST", f"/pos/{po1['id']}/invoices", AISHA, {"invoice_no": "MS-1", "invoice_date": D(0), "amount": "1000.00"}), "invoice 1")
    ok(H("POST", f"/invoices/{inv1['id']}/verify", KWAME, {}), "verify 1")
    rq2, po2 = order("LAB", "MEDICAL_SUPPLIES", "Reagent packs", "20", "50.00")
    ok(H("POST", f"/pos/{po2['id']}/receive", AISHA, {"delivery_note": "DN-2001", "lines": [{"line_no": 1, "qty": "8"}]}), "receive 2")
    inv2 = ok(H("POST", f"/pos/{po2['id']}/invoices", AISHA, {"invoice_no": "MS-2", "invoice_date": D(0), "amount": "900.00"}), "invoice 2")
    rq3, po3 = order("ADM", "ADMINISTRATION", "Printer paper", "5", "40.00", approve=False)
    return {"fid": fid, "dept": dept, "po1": po1, "po2": po2, "po3": po3, "inv1": inv1, "inv2": inv2, "rq1": rq1}
