"""Offline release-readiness check. Run it before you commit a release:

    python3 scripts/release_check.py

It only LOOKS (reads files, compiles code, parses migrations); it never connects to a database or the network and prints no secret values.
Exit code 0 means every check below passed. It does NOT mean the release is production-ready: see the NOT CHECKED list it prints."""
import ast
import glob
import os
import py_compile
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
results = []   # (status, name, detail)


def add(ok, name, detail=""):
    results.append(("PASS" if ok else "FAIL", name, detail))


def rel(p): return os.path.relpath(p, ROOT)


def python_compiles():
    bad = []
    with tempfile.TemporaryDirectory() as tmp:
        for f in glob.glob(os.path.join(ROOT, "src", "**", "*.py"), recursive=True) + glob.glob(os.path.join(ROOT, "scripts", "*.py")) + glob.glob(os.path.join(ROOT, "migrations", "**", "*.py"), recursive=True):
            try:
                py_compile.compile(f, cfile=os.path.join(tmp, "x.pyc"), doraise=True)
            except py_compile.PyCompileError as exc:
                bad.append(f"{rel(f)}: {exc.msg.splitlines()[-1]}")
    add(not bad, "every Python file compiles", "; ".join(bad[:5]))


def js_compiles():
    node = subprocess.run(["node", "--version"], capture_output=True)
    if node.returncode != 0:
        results.append(("SKIP", "every frontend JavaScript file parses", "node is not installed")); return
    bad = []
    for f in glob.glob(os.path.join(ROOT, "frontend", "src", "**", "*.js"), recursive=True):
        with tempfile.TemporaryDirectory() as tmp:
            c = os.path.join(tmp, "x.mjs")
            with open(f) as src, open(c, "w") as dst: dst.write(src.read())
            r = subprocess.run(["node", "--check", c], capture_output=True, text=True)
            if r.returncode != 0: bad.append(f"{rel(f)}: {r.stderr.strip().splitlines()[0] if r.stderr.strip() else 'syntax error'}")
    add(not bad, "every frontend JavaScript file parses", "; ".join(bad[:5]))


def single_migration_head():
    revs = {}
    for f in glob.glob(os.path.join(ROOT, "migrations", "versions", "*.py")):
        s = open(f).read()
        r = re.search(r'^revision: str = "(\w+)"', s, re.M); d = re.search(r'^down_revision: Union\[str, None\] = (None|"(\w+)")', s, re.M)
        if r and d: revs[r.group(1)] = d.group(2)
    heads = set(revs) - {d for d in revs.values() if d}
    roots = [r for r, d in revs.items() if d is None]
    missing = [d for d in revs.values() if d and d not in revs]
    sql_missing = []
    for f in glob.glob(os.path.join(ROOT, "migrations", "versions", "*.py")):
        stem = os.path.basename(f)[:-3]
        if stem.split("_")[0] != "9ab0a651f090" and not (os.path.exists(os.path.join(ROOT, "migrations", "sql", stem + ".up.sql")) and os.path.exists(os.path.join(ROOT, "migrations", "sql", stem + ".down.sql"))):
            sql_missing.append(stem)
    add(len(heads) == 1 and len(roots) == 1 and not missing and not sql_missing, "migrations form one chain with one head, each with reviewed up/down SQL",
        f"heads={sorted(heads)} roots={roots} missing={missing} no-sql={sql_missing}")
    pre = open(os.path.join(ROOT, "scripts", "db_preflight.py")).read()
    add(bool(heads) and f'HEAD = "{next(iter(heads))}"' in pre, "db_preflight.py knows the current migration head")


def routers_are_mounted():
    main = open(os.path.join(ROOT, "src", "asavexa", "api", "main.py")).read()
    unmounted = []
    for f in sorted(glob.glob(os.path.join(ROOT, "src", "asavexa", "api", "routers", "*.py"))):
        name = os.path.basename(f)[:-3]
        if name == "__init__" or "APIRouter(" not in open(f).read():
            continue
        if not re.search(rf"include_router\(\s*{name}\.", main):
            unmounted.append(name)
    add(not unmounted, "every router module is mounted in main.py", ", ".join(unmounted))


SECRET_PATTERNS = [
    (r"-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----", "private key"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key id"),
    (r"\bsk-[A-Za-z0-9]{32,}", "API key"),
    (r"\bpostgres(ql)?://[^\s:@/]+:(?!(?:pass|password|PASS|PASSWORD|secret|changeme|xxx+)@)[^\s:@/$<{]{4,}@(?!localhost|127\.0\.0\.1|db\b|postgres\b)[^\s/]+", "database URL with a password"),
    (r"\bre_[A-Za-z0-9]{20,}", "email-provider key"),
]
SKIP_DIRS = {".git", "node_modules", "__pycache__", "images"}


def no_secrets():
    hits = []
    for dirpath, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if fn.endswith((".png", ".jpg", ".zip", ".pyc", ".db", ".gz", ".woff2", ".ico")):
                continue
            p = os.path.join(dirpath, fn)
            try:
                text = open(p, errors="ignore").read()
            except OSError:
                continue
            for pat, label in SECRET_PATTERNS:
                if re.search(pat, text):
                    hits.append(f"{rel(p)} ({label})")
    add(not hits, "no secret-looking values in the repository (values are never printed)", "; ".join(hits[:8]))
    add(not os.path.exists(os.path.join(ROOT, ".env")), "no .env file in the release folder")
    gi = open(os.path.join(ROOT, ".gitignore")).read() if os.path.exists(os.path.join(ROOT, ".gitignore")) else ""
    add(all(x in gi for x in (".env", "*.db", "docs/images/landing/")), ".gitignore keeps .env, databases and landing screenshots out of commits")


def docs_present():
    need = ["DEPLOYMENT.md", "docs/stage1-migrations.md", "docs/evidence-review.md", "docs/stage5-ai-evaluation.md", "docs/stage6-standards-registry.md",
            "docs/stage7-agents.md", "docs/stage9-rate-limiting.md", "docs/stage10-14.md", "docs/stage15-entity-config.md", "docs/stage16-treasury.md", "docs/stage17-procurement.md", "docs/stage18-fpa.md", "docs/stage22-aigov.md", "docs/stage24-secretarial.md", "docs/stage25-fixedassets.md", "docs/stage26-inventory.md", "docs/stage27-investments.md", "docs/stage28-valuation.md", "docs/stage29-insurance.md", "docs/stage30-esg.md", "docs/stage31-payroll.md", "docs/stage32-projects.md", "docs/stage33-datagov.md", "docs/stage34-oprs.md", "docs/stage35-impact.md", "docs/stage36-insolvency.md", "docs/stage37-pension.md", "docs/stage38-franchise.md", "docs/stage39-mergers.md", "docs/stage41-approvals.md", "docs/stage40-superseded.md", "docs/stage23-quality.md", "docs/stage19-fincrime.md", "docs/stage20-itaudit.md", "docs/stage21-resilience.md", "docs/stage8-release.md", ".github/workflows/ci.yml"]
    missing = [n for n in need if not os.path.exists(os.path.join(ROOT, n))]
    add(not missing, "release documents and CI workflow are present", ", ".join(missing))


def tests_exist_for_new_modules():
    missing = [n for n in ("tests/test_evidence_review.py", "tests/test_ai_evaluation.py", "tests/test_standards_registry.py", "tests/test_agents.py", "tests/test_rate_limit_shared.py",
                           "frontend/tests/evidence-review.test.js", "frontend/tests/standards-registry.test.js", "frontend/tests/agents.test.js") if not os.path.exists(os.path.join(ROOT, n))]
    add(not missing, "every new module has its tests", ", ".join(missing))


NOT_CHECKED = [
    "That the test suites pass: run them (docs/stage8-release.md lists the commands).",
    "FastAPI, SQLAlchemy and Alembic behaviour: CI's 'Real stack' job does that and has never been run.",
    "The production database: run scripts/db_preflight.py against it yourself, and take a verified backup first.",
    "Render and Vercel settings, environment variables, email provider, domain and TLS.",
    "Load, performance, accessibility audits and an independent security review.",
]


def main():
    for fn in (python_compiles, js_compiles, single_migration_head, routers_are_mounted, no_secrets, docs_present, tests_exist_for_new_modules):
        try:
            fn()
        except Exception as exc:     # a crashing check is a failing check, never a silent pass
            add(False, fn.__name__, f"check crashed: {type(exc).__name__}: {exc}")
    for status, name, detail in results:
        print(f"{status:4s} {name}" + (f"\n       {detail}" if detail and status != "PASS" else ""))
    failed = [r for r in results if r[0] == "FAIL"]
    print("\nNOT CHECKED by this script:"); [print("  - " + n) for n in NOT_CHECKED]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks passed." + ("" if not failed else f" {len(failed)} FAILED."))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
