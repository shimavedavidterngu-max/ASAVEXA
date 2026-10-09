"""Encrypted database backups and verified restores.

A backup is a PostgreSQL custom-format dump (pg_dump), encrypted with the platform key ring (AES-256-GCM, same envelope as evidence
files), plus a small manifest holding its checksum. Connection details are passed to pg_dump through environment variables, never on the
command line, so they do not appear in process listings or logs.

Honest limits: the dump is held in memory while it is encrypted (fine for pilot-sized databases; the script warns above ~1 GB), and a
backup is only as good as its last tested restore, so `verify_backup` and `restore_backup` are first-class."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import urllib.parse
from datetime import datetime, timezone
from typing import Callable, Optional

from . import crypto
from .errors import DecryptionError, SecurityError, StorageError, ValidationError

AAD_ORG = "system"
WARN_BYTES = 1_000_000_000
MANIFEST_SUFFIX = ".json"


class BackupError(SecurityError):
    status = 500


def _utc():
    return datetime.now(timezone.utc)


def pg_env(url: str) -> dict:
    """libpq environment for a SQLAlchemy-style URL (postgresql+psycopg://user:pass@host:port/db?sslmode=require)."""
    u = urllib.parse.urlparse(url.replace("postgresql+psycopg://", "postgresql://").replace("postgres://", "postgresql://"))
    if u.scheme != "postgresql" or not u.hostname or not u.path.strip("/"):
        raise ValidationError("The database address is not a PostgreSQL address.")
    env = {"PGHOST": u.hostname, "PGPORT": str(u.port or 5432), "PGUSER": urllib.parse.unquote(u.username or ""),
           "PGPASSWORD": urllib.parse.unquote(u.password or ""), "PGDATABASE": u.path.lstrip("/")}
    q = urllib.parse.parse_qs(u.query)
    if "sslmode" in q:
        env["PGSSLMODE"] = q["sslmode"][0]
    return env


def _tool(name: str) -> str:
    p = shutil.which(name)
    if not p:
        raise BackupError(f"{name} is not installed on this machine. Install the PostgreSQL client tools (matching the server's major version).")
    return p


def _run(cmd, env_extra: dict, stdin: Optional[bytes] = None) -> bytes:
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "TMPDIR", "SYSTEMROOT")}
    env.update(env_extra)
    r = subprocess.run(cmd, input=stdin, capture_output=True, env=env, timeout=3600)
    if r.returncode != 0:
        msg = r.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
        raise BackupError(f"{os.path.basename(cmd[0])} failed: {' | '.join(msg)}"[:600])
    return r.stdout


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def create_backup(db_url: str, keys, out_dir: str, objects=None, now: Callable[[], datetime] = _utc, keep: int = 14) -> dict:
    """Dump, encrypt, checksum, write manifest, optionally copy to object storage, prune old local copies. Returns the manifest."""
    if keys is None:
        raise ValidationError("Backups are encrypted, so they need the platform keys (ASAVEXA_KEYS).")
    os.makedirs(out_dir, exist_ok=True)
    plain = _run([_tool("pg_dump"), "--format=custom", "--no-owner", "--no-privileges"], pg_env(db_url))
    if not plain:
        raise BackupError("pg_dump produced no data.")
    stamp = now().strftime("%Y%m%dT%H%M%SZ")
    name = f"asavexa-{stamp}.dump.enc"
    ct, header = crypto.encrypt_blob(keys, plain, AAD_ORG, f"backup:{name}")
    manifest = {"name": name, "created_at": now().isoformat(), "format": "pg_dump custom, AES-256-GCM envelope", "key_id": header["kid"],
                "header": header, "ciphertext_sha256": _sha(ct), "ciphertext_bytes": len(ct), "plaintext_sha256": _sha(plain),
                "plaintext_bytes": len(plain), "pg_dump_version": _run([_tool("pg_dump"), "--version"], {}).decode().strip(), "stored_in": ["local"],
                "large": len(plain) > WARN_BYTES}
    path = os.path.join(out_dir, name)
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(ct)
    os.replace(tmp, path)
    if objects is not None:
        try:
            objects.put(f"system/backups/{name}", ct)
            manifest["stored_in"].append(objects.name)
            objects.put("system/backups/latest.json", json.dumps(_public(manifest)).encode())
        except Exception as e:                            # the local copy stands; say so instead of pretending
            manifest["upload_error"] = f"{type(e).__name__}: {str(e)[:200]}"
    with open(path + MANIFEST_SUFFIX, "w") as f:
        json.dump(manifest, f, indent=2)
    _prune(out_dir, keep)
    return manifest


def _public(m: dict) -> dict:
    return {k: v for k, v in m.items() if k not in ("header",)}


def _prune(out_dir: str, keep: int) -> None:
    files = sorted(f for f in os.listdir(out_dir) if f.startswith("asavexa-") and f.endswith(".dump.enc"))
    for old in files[:-keep] if keep > 0 else []:
        for suffix in ("", MANIFEST_SUFFIX):
            try:
                os.remove(os.path.join(out_dir, old + suffix))
            except OSError:
                pass


def load_manifest(path: str) -> dict:
    mp = path if path.endswith(MANIFEST_SUFFIX) else path + MANIFEST_SUFFIX
    try:
        with open(mp) as f:
            return json.load(f)
    except (OSError, ValueError):
        raise BackupError(f"Could not read the backup manifest {os.path.basename(mp)}.")


def decrypt_backup(path: str, keys, manifest: Optional[dict] = None) -> bytes:
    """Checks the checksum, then decrypts, then checks the plaintext checksum. Raises with a plain reason if anything is off."""
    path = path[:-len(MANIFEST_SUFFIX)] if path.endswith(MANIFEST_SUFFIX) else path
    m = manifest or load_manifest(path)
    with open(path, "rb") as f:
        ct = f.read()
    if _sha(ct) != m["ciphertext_sha256"]:
        raise BackupError("The backup file does not match its recorded checksum: it is damaged or was changed.")
    try:
        plain = crypto.decrypt_blob(keys, ct, m["header"], AAD_ORG, f"backup:{m['name']}")
    except DecryptionError as e:
        raise BackupError(f"The backup could not be decrypted ({e}). Check that the same ASAVEXA_KEYS are loaded.")
    if _sha(plain) != m["plaintext_sha256"]:
        raise BackupError("The decrypted backup does not match its recorded checksum.")
    return plain


def verify_backup(path: str, keys) -> dict:
    """Proves the backup can be read: checksum + decrypt + pg_restore can list its contents. Does NOT touch any database."""
    plain = decrypt_backup(path, keys)
    out = _run([_tool("pg_restore"), "--list"], {}, stdin=plain).decode("utf-8", "replace")
    tables = [ln for ln in out.splitlines() if " TABLE DATA " in ln]
    return {"ok": True, "tables_in_backup": len(tables), "bytes": len(plain)}


def restore_backup(path: str, keys, target_url: str, live_url: Optional[str] = None, allow_live: bool = False) -> dict:
    """Restores into `target_url`. Refuses to touch the live database unless allow_live is set; the normal drill restores into a new empty database."""
    if live_url and _same_db(target_url, live_url) and not allow_live:
        raise ValidationError("That is the live database. Restore into a new, empty database first (a drill), or pass the explicit overwrite flag.")
    plain = decrypt_backup(path, keys)
    args = [_tool("pg_restore"), "--no-owner", "--no-privileges", "--exit-on-error"]
    if allow_live:
        args += ["--clean", "--if-exists"]
    with tempfile.NamedTemporaryFile(delete=False) as t:
        t.write(plain); tmp = t.name
    try:
        os.chmod(tmp, 0o600)
        _run(args + ["--dbname", pg_env(target_url)["PGDATABASE"], tmp], pg_env(target_url))
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return {"restored": True, "bytes": len(plain)}


def _same_db(a: str, b: str) -> bool:
    ea, eb = pg_env(a), pg_env(b)
    return all(ea.get(k) == eb.get(k) for k in ("PGHOST", "PGPORT", "PGDATABASE"))


def latest_backup(out_dir: str) -> Optional[dict]:
    if not os.path.isdir(out_dir):
        return None
    ms = sorted(f for f in os.listdir(out_dir) if f.startswith("asavexa-") and f.endswith(".dump.enc" + MANIFEST_SUFFIX))
    return _public(load_manifest(os.path.join(out_dir, ms[-1]))) if ms else None


def status(out_dir: str, max_age_hours: int = 26, now: Callable[[], datetime] = _utc) -> dict:
    """Plain-language backup freshness for monitoring."""
    m = latest_backup(out_dir)
    if m is None:
        return {"ok": False, "detail": "No backup has been made yet."}
    age = now() - datetime.fromisoformat(m["created_at"])
    hours = age.total_seconds() / 3600
    return {"ok": hours <= max_age_hours, "latest": m["name"], "age_hours": round(hours, 1),
            "detail": f"Latest backup is {hours:.1f} hours old." + ("" if hours <= max_age_hours else " That is older than expected."), "stored_in": m.get("stored_in")}
