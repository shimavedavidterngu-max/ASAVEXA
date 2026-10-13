"""Runs every browser journey against a fresh test server each time. Exit code 0 only if every journey passes.

    pip install playwright && playwright install chromium
    PYTHONPATH=src:tests python3 e2e/run_all.py

Journeys are independent: each gets a new server (new in-memory database). Set CHROMIUM_PATH to use a specific Chromium."""
import glob
import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(ROOT, "src"), os.path.join(ROOT, "tests")]), PYTHONWARNINGS="ignore")
results = {}
for journey in sorted(glob.glob(os.path.join(HERE, "journey_*.py"))):
    server = subprocess.Popen([sys.executable, os.path.join(HERE, "server.py")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    try:
        r = subprocess.run([sys.executable, journey], env=env, cwd=HERE, timeout=500)
        results[os.path.basename(journey)] = r.returncode
    finally:
        server.send_signal(signal.SIGTERM); server.wait(timeout=10)
print("\nSUMMARY"); [print(("OK   " if rc == 0 else "FAIL ") + n) for n, rc in results.items()]
sys.exit(0 if results and all(rc == 0 for rc in results.values()) else 1)
