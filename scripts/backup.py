"""Make an encrypted backup of the ASAVEXA database.

    python scripts/backup.py                 # writes into ./backups  (or BACKUP_DIR)
    python scripts/backup.py --verify        # also proves the new backup can be read

Needs: DATABASE_URL, ASAVEXA_KEYS, ASAVEXA_CURRENT_KEY, and the PostgreSQL client tools (pg_dump, pg_restore).
If ASAVEXA_STORAGE=s3 the backup is copied to the bucket as well."""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from asavexa.security import backup  # noqa: E402
from asavexa.security.crypto import LocalKeyring  # noqa: E402
from asavexa.security.errors import SecurityError  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.environ.get("BACKUP_DIR", "backups"))
    ap.add_argument("--keep", type=int, default=14, help="how many local backups to keep")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set."); return 2
    try:
        keys = LocalKeyring.from_env()
        if keys is None:
            print("ASAVEXA_KEYS is not set. Backups are always encrypted."); return 2
        objects = None
        if (os.environ.get("ASAVEXA_STORAGE") or "").lower() == "s3":
            from asavexa.security.objectstore import S3ObjectStore
            objects = S3ObjectStore.from_env()
        m = backup.create_backup(url, keys, a.out, objects=objects, keep=a.keep)
        print(f"Backup written: {os.path.join(a.out, m['name'])}  ({m['plaintext_bytes']:,} bytes before encryption)")
        print("Stored in:", ", ".join(m["stored_in"]))
        if m.get("upload_error"):
            print("WARNING: copy to object storage failed:", m["upload_error"])
        if a.verify:
            print("Verified:", backup.verify_backup(os.path.join(a.out, m["name"]), keys))
        return 0
    except SecurityError as e:
        print("FAILED:", e); return 1


if __name__ == "__main__":
    sys.exit(main())
