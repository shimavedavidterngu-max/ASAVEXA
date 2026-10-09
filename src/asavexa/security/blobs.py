"""Encrypted evidence files: encrypt -> store in object storage -> record how to decrypt. Only ciphertext leaves the app."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Callable, Optional

from . import crypto
from .errors import DecryptionError, NotFoundError, ResidencyError, StorageError
from .objectstore import ObjectStore
from .store import DocStore


def _utc():
    return datetime.now(timezone.utc)


class BlobService:
    def __init__(self, store: DocStore, objects: ObjectStore, keys, residency=None, now: Callable[[], datetime] = _utc):
        """residency: optional object with check_storage(org_id, region) that raises ResidencyError."""
        self.store, self.objects, self.keys, self.residency, self.now = store, objects, keys, residency, now

    @staticmethod
    def object_key(org_id: str, evidence_id: str) -> str:
        return f"org/{org_id}/evidence/{evidence_id}"

    def put(self, org_id: str, evidence_id: str, content: bytes) -> dict:
        if self.residency is not None:
            self.residency.check_storage(org_id, self.objects.data_region)
        ct, header = crypto.encrypt_blob(self.keys, content, org_id, evidence_id)
        key = self.object_key(org_id, evidence_id)
        self.objects.put(key, ct)
        meta = {"org_id": org_id, "evidence_id": evidence_id, "backend": self.objects.name, "region": self.objects.data_region, "object_key": key,
                "header": header, "size": len(content), "sha256": hashlib.sha256(content).hexdigest(),
                "cipher_sha256": hashlib.sha256(ct).hexdigest(), "stored_at": self.now().isoformat(), "state": "STORED"}
        self.store.put("blob", evidence_id, meta, org_id=org_id)
        return self.public(meta)

    def _meta(self, org_id: str, evidence_id: str) -> dict:
        m = self.store.get("blob", evidence_id)
        if m is None or m["org_id"] != org_id:          # another organisation's file is simply "not found"
            raise NotFoundError("No stored file for this evidence record.")
        return m

    @staticmethod
    def public(m: dict) -> dict:
        return {k: m.get(k) for k in ("evidence_id", "backend", "region", "size", "sha256", "stored_at", "state", "shredded_at", "shred_reason")} | {"key_id": (m.get("header") or {}).get("kid")}

    def info(self, org_id: str, evidence_id: str) -> Optional[dict]:
        m = self.store.get("blob", evidence_id)
        return self.public(m) if m and m["org_id"] == org_id else None

    def get(self, org_id: str, evidence_id: str) -> bytes:
        m = self._meta(org_id, evidence_id)
        if m["state"] == "SHREDDED":
            raise NotFoundError("This file was permanently disposed of under the retention policy. Its record and fingerprint remain.")
        ct = self.objects.get(m["object_key"])
        if hashlib.sha256(ct).hexdigest() != m["cipher_sha256"]:
            raise DecryptionError("The stored file failed its integrity check. It was changed or damaged.")
        plain = crypto.decrypt_blob(self.keys, ct, m["header"], org_id, evidence_id)
        if hashlib.sha256(plain).hexdigest() != m["sha256"]:
            raise DecryptionError("The stored file does not match its recorded fingerprint.")
        return plain

    def verify(self, org_id: str, evidence_id: str) -> dict:
        try:
            self.get(org_id, evidence_id)
            return {"evidence_id": evidence_id, "ok": True}
        except (DecryptionError, NotFoundError, StorageError) as e:
            return {"evidence_id": evidence_id, "ok": False, "problem": str(e)}

    def shred(self, org_id: str, evidence_id: str, reason: str) -> dict:
        """Permanent disposal: delete the ciphertext AND the wrapped data key, so even a surviving copy cannot be decrypted."""
        m = self._meta(org_id, evidence_id)
        if m["state"] != "SHREDDED":
            self.objects.delete(m["object_key"])
            m["header"] = {"alg": m["header"]["alg"], "kid": m["header"]["kid"]}
            m.update(state="SHREDDED", shredded_at=self.now().isoformat(), shred_reason=reason)
            self.store.put("blob", evidence_id, m, org_id=org_id)
        return self.public(m)

    def rotate(self, org_id: Optional[str] = None, to_key_id: Optional[str] = None) -> dict:
        """Re-wraps every stored data key under the current key. Files are not touched. Safe to run repeatedly."""
        done = skipped = failed = 0
        target = to_key_id or self.keys.current_key_id
        for eid, m in self.store.list("blob", org_id=org_id):
            if m["state"] != "STORED" or m["header"].get("kid") == target:
                skipped += 1; continue
            try:
                m["header"] = crypto.rewrap(self.keys, m["header"], m["org_id"], eid, target)
                self.store.put("blob", eid, m, org_id=m["org_id"]); done += 1
            except DecryptionError:
                failed += 1
        return {"rotated": done, "already_current": skipped, "failed": failed, "target_key": target}

    def keys_in_use(self, org_id: Optional[str] = None) -> dict:
        use = {}
        for _, m in self.store.list("blob", org_id=org_id):
            if m["state"] == "STORED":
                use[m["header"]["kid"]] = use.get(m["header"]["kid"], 0) + 1
        return use
