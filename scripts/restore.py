"""Restore an ASAVEXA backup into a database. The safe routine is a DRILL into a new, empty database.

    python scripts/restore.py backups/asavexa-20261009T020000Z.dump.enc --verify-only
    python scripts/restore.py backups/asavexa-....dump.enc --target postgresql://user:pass@host:5432/asavexa_drill

Needs ASAVEXA_KEYS (the same keys the backup was made with). It refuses to touch the live DATABASE_URL unless --overwrite-live is given."""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from asavexa.security import backup  # noqa: E402
from asavexa.security.crypto import LocalKeyring  # noqa: E402
from asavexa.security.errors import SecurityError  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("backup_file")
    ap.add_argument("--target", help="database address to restore into")
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--overwrite-live", action="store_true")
    a = ap.parse_args()
    try:
        keys = LocalKeyring.from_env()
        if keys is None:
            print("ASAVEXA_KEYS is not set."); return 2
        if a.verify_only or not a.target:
            print("Backup can be read:", backup.verify_backup(a.backup_file, keys))
            if not a.target:
                return 0
            return 0
        print(backup.restore_backup(a.backup_file, keys, a.target, live_url=os.environ.get("DATABASE_URL"), allow_live=a.overwrite_live))
        return 0
    except SecurityError as e:
        print("FAILED:", e); return 1


if __name__ == "__main__":
    sys.exit(main())
