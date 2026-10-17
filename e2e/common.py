"""Shared helpers for the browser journeys. Needs Playwright with Chromium: pip install playwright && playwright install chromium."""
import json as _j
import os
import subprocess
import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_PORT, WEB_PORT = int(os.environ.get("E2E_BACKEND_PORT", 8790)), int(os.environ.get("E2E_WEB_PORT", 5173))   # the overrides let a second journey run beside the first
BASE = f"http://127.0.0.1:{BACKEND_PORT}"
URL = f"http://localhost:{WEB_PORT}/index.html"
CHROMIUM = os.environ.get("CHROMIUM_PATH")          # leave unset to use Playwright's own browser
DARA = ("dara@meridian.test", "correct horse battery staple1")    # owner
KWAME = ("kwame@meridian.test", "still-another-password1")        # approver
AISHA = ("aisha@meridian.test", "yet-another-password1")          # accountant
TUNDE = ("tunde@meridian.test", "tester-password-two1")           # administrator: can prepare IT-audit work, nothing else here
OTHER = ("other@other.test", "unrelated-password1")               # a different company's owner
fails = []
web = None


def start_web():
    global web
    web = subprocess.Popen([sys.executable, "-m", "http.server", str(WEB_PORT), "--directory", os.path.join(ROOT, "frontend")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop_web():
    if web:
        web.terminate()


def launch(p):
    return p.chromium.launch(executable_path=CHROMIUM) if CHROMIUM else p.chromium.launch()


def handle(route):
    """The frontend calls the production API address; send those calls to the local test server instead."""
    req = route.request; path = req.url.replace("https://asavexa.onrender.com", "")
    hdr = {"access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*"}
    if req.method == "OPTIONS": return route.fulfill(status=204, headers=hdr)
    r = urllib.request.Request(BASE + path, data=req.post_data_buffer, method=req.method, headers={k: v for k, v in req.headers.items() if k in ("authorization", "content-type", "user-agent")})
    try: resp = urllib.request.urlopen(r); code, body, h = resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e: code, body, h = e.code, e.read(), dict(e.headers)
    hdr["content-type"] = h.get("Content-Type", "application/json"); route.fulfill(status=code, headers=hdr, body=body)


def check(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + (("  -> " + str(extra)[:600]) if (extra and not ok) else ""))
    if not ok: fails.append(name)


def txt(page, sel):
    return (page.locator(sel).first.text_content() or "") if page.locator(sel).count() else ""


def sign_in(page, email, pw, org):
    page.goto("about:blank"); page.goto(URL); page.evaluate("sessionStorage.clear(); localStorage.clear()"); page.goto("about:blank"); page.goto(URL + "#/"); page.wait_for_timeout(700)
    page.click("#ld-signin"); page.wait_for_timeout(300)
    page.fill("#email", email); page.fill("#password", pw); page.click("button[type=submit]"); page.wait_for_timeout(1200)
    if page.locator(".app-shell").count() == 0:
        page.locator("#ob-picker [data-org], .card[role=button]", has_text=org).first.click(); page.wait_for_timeout(1500)
    page.wait_for_timeout(1500)


def api(method, path, creds, org_name, body=None):
    """Calls the test server directly as a signed-in person (used for the test-only hooks and cross-company checks)."""
    def call(m, p, tok=None, b=None):
        r = urllib.request.Request(BASE + p, data=(_j.dumps(b).encode() if b is not None else None), method=m, headers={"content-type": "application/json", **({"authorization": "Bearer " + tok} if tok else {})})
        try: return _j.loads(urllib.request.urlopen(r).read() or b"{}")
        except urllib.error.HTTPError as e: return {"status": e.code, "body": e.read().decode()}
    t = call("POST", "/auth/login", b={"email": creds[0], "password": creds[1]})["token"]
    oid = [o["id"] for o in call("GET", "/organisations/mine", t) if org_name in o["name"]][0]
    call("POST", "/auth/select-organisation", t, {"org_id": oid})
    return call(method, path, t, body)


def goto(page, hash_path):
    page.goto(f"{URL}#{hash_path}"); page.wait_for_timeout(2300)


def session():
    """Context manager-ish: returns (playwright, browser, page, errors) ready to use."""
    p = sync_playwright().start(); b = launch(p); errs = []
    page = b.new_context(viewport={"width": 1300, "height": 2200}).new_page()
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.on("console", lambda m: errs.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
    page.route("https://asavexa.onrender.com/**", handle)
    return p, b, page, errs


def finish(p, b):
    b.close(); p.stop(); stop_web()
    print("FAILS:", fails)
    sys.exit(1 if fails else 0)
