"""Levels 7-8 (data shapes only): bank-API and payment-platform payloads become staged bank transactions.

IMPORTANT: this file reads PAYLOADS (a JSON export or a saved API response). It does not call any provider. Live
connections need each provider's credentials and consent flow, which cannot be created or tested from here, and the
payload shapes below follow each provider's published documentation and have NOT been checked against a live account.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import model as M
from .bank import finish_bank_batch
from .errors import IngestionError, UnsupportedFileError
from .util import AmountError, clean, parse_amount

ZERO = Decimal("0.00")
ZERO_DECIMAL = {"BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"}
THREE_DECIMAL = {"BHD", "JOD", "KWD", "OMR", "TND"}

PROVIDERS = {
    "PAYSTACK": "Paystack (transactions list)", "FLUTTERWAVE": "Flutterwave (transactions list)", "STRIPE": "Stripe (balance transactions)",
    "PLAID": "Plaid (transactions)", "OPEN_BANKING_UK": "UK Open Banking (account transactions)",
}


def _minor(v, currency: str) -> Decimal:
    if currency in THREE_DECIMAL:
        raise AmountError(f"{currency} uses three decimal places, which ASAVEXA does not support")
    d = Decimal(str(v))
    if d != d.to_integral_value():
        raise AmountError(f"{v} is not a whole number of minor units")
    return (d / (Decimal(1) if currency in ZERO_DECIMAL else Decimal(100))).quantize(Decimal("0.01"))


def _iso_date(s) -> Optional[date]:
    s = clean(s)
    if not s:
        return None
    try:
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            return date.fromisoformat(s[:10])
    except ValueError:
        return None
    return None


def detect_provider(payload: Any) -> Optional[str]:
    if isinstance(payload, dict):
        d = payload.get("data")
        if isinstance(d, list) and d and isinstance(d[0], dict):
            f = d[0]
            if "reference" in f and "paid_at" in f or ("channel" in f and "amount" in f and "domain" in f):
                return "PAYSTACK"
            if "tx_ref" in f or "flw_ref" in f:
                return "FLUTTERWAVE"
            if f.get("object") == "balance_transaction" or ("net" in f and "fee" in f and "created" in f):
                return "STRIPE"
        if payload.get("object") == "list" and isinstance(d, list):
            return "STRIPE"
        if isinstance(payload.get("transactions"), list) and (not payload["transactions"] or "transaction_id" in payload["transactions"][0]):
            return "PLAID"
        dd = payload.get("Data")
        if isinstance(dd, dict) and isinstance(dd.get("Transaction"), list):
            return "OPEN_BANKING_UK"
        if isinstance(payload.get("data"), list) and not payload["data"]:
            return None
    return None


def _entry(n, d, desc, ref, amt: Decimal, cur, issues=None):
    return {"row": n, "date": d, "value_date": None, "description": desc, "reference": ref, "money_in": amt if amt > 0 else ZERO,
            "money_out": -amt if amt < 0 else ZERO, "balance": None, "currency": cur, "issues": issues or []}


def _paystack(p) -> List[dict]:
    out = []
    for n, t in enumerate(p.get("data") or [], 1):
        if clean(t.get("status")) != "success":
            continue
        cur = clean(t.get("currency")).upper() or None
        d = _iso_date(t.get("paid_at") or t.get("transaction_date") or t.get("createdAt"))
        iss = [] if d else [M.issue(M.ERROR, f"Item {n}: no readable payment date.", n, "date")]
        try:
            gross = _minor(t.get("amount"), cur or "NGN")
            fee = _minor(t.get("fees") or 0, cur or "NGN")
        except (AmountError, Exception) as e:
            out.append(_entry(n, d, "", None, ZERO, cur, [M.issue(M.ERROR, f"Item {n}: {e}", n, "amount")])); continue
        who = clean((t.get("customer") or {}).get("email"))
        ref = clean(t.get("reference")) or clean(t.get("id")) or None
        out.append(_entry(n, d, f"Paystack payment {who}".strip(), ref, gross, cur, iss))
        if fee > 0:
            out.append(_entry(n, d, f"Paystack fee for {ref or n}", f"{ref}-FEE" if ref else None, -fee, cur, list(iss)))
    return out


def _flutterwave(p) -> List[dict]:
    out = []
    for n, t in enumerate(p.get("data") or [], 1):
        if clean(t.get("status")).lower() not in ("successful", "success", "completed"):
            continue
        cur = clean(t.get("currency")).upper() or None
        d = _iso_date(t.get("created_at"))
        iss = [] if d else [M.issue(M.ERROR, f"Item {n}: no readable date.", n, "date")]
        try:
            gross = parse_amount(t.get("amount")) or ZERO
            fee = parse_amount(t.get("app_fee")) or ZERO
        except AmountError as e:
            out.append(_entry(n, d, "", None, ZERO, cur, [M.issue(M.ERROR, f"Item {n}: {e}", n, "amount")])); continue
        ref = clean(t.get("tx_ref")) or clean(t.get("flw_ref")) or clean(t.get("id")) or None
        who = clean((t.get("customer") or {}).get("email"))
        out.append(_entry(n, d, f"Flutterwave payment {who}".strip(), ref, gross, cur, iss))
        if fee > 0:
            out.append(_entry(n, d, f"Flutterwave fee for {ref or n}", f"{ref}-FEE" if ref else None, -fee, cur, list(iss)))
    return out


def _stripe(p) -> List[dict]:
    out = []
    for n, t in enumerate(p.get("data") or [], 1):
        cur = clean(t.get("currency")).upper() or None
        try:
            d = datetime.fromtimestamp(int(t["created"]), tz=timezone.utc).date()
            iss = []
        except (KeyError, TypeError, ValueError, OverflowError):
            d, iss = None, [M.issue(M.ERROR, f"Item {n}: no readable date.", n, "date")]
        try:
            amt = _minor(t.get("amount"), cur or "USD")
            fee = _minor(t.get("fee") or 0, cur or "USD")
        except (AmountError, Exception) as e:
            out.append(_entry(n, d, "", None, ZERO, cur, [M.issue(M.ERROR, f"Item {n}: {e}", n, "amount")])); continue
        ref = clean(t.get("id")) or None
        desc = clean(t.get("description")) or f"Stripe {clean(t.get('type')) or 'transaction'}"
        out.append(_entry(n, d, f"Stripe {t.get('type', '')}: {desc}".strip(), ref, amt, cur, iss))
        if fee > 0:
            out.append(_entry(n, d, f"Stripe fee for {ref or n}", f"{ref}-FEE" if ref else None, -fee, cur, list(iss)))
    return out


def _plaid(p) -> List[dict]:
    out = []
    for n, t in enumerate(p.get("transactions") or [], 1):
        if t.get("pending"):
            continue
        cur = clean(t.get("iso_currency_code")).upper() or None
        d = _iso_date(t.get("date"))
        iss = [] if d else [M.issue(M.ERROR, f"Item {n}: no readable date.", n, "date")]
        try:
            raw = parse_amount(t.get("amount")) or ZERO
        except AmountError as e:
            out.append(_entry(n, d, "", None, ZERO, cur, [M.issue(M.ERROR, f"Item {n}: {e}", n, "amount")])); continue
        # Plaid: a POSITIVE amount is money leaving the account.
        out.append(_entry(n, d, clean(t.get("merchant_name") or t.get("name")), clean(t.get("transaction_id")) or None, -raw, cur, iss))
    return out


def _open_banking(p) -> List[dict]:
    out = []
    for n, t in enumerate((p.get("Data") or {}).get("Transaction") or [], 1):
        if clean(t.get("Status")) and clean(t.get("Status")).lower() != "booked":
            continue
        a = t.get("Amount") or {}
        cur = clean(a.get("Currency")).upper() or None
        d = _iso_date(t.get("BookingDateTime"))
        iss = [] if d else [M.issue(M.ERROR, f"Item {n}: no readable booking date.", n, "date")]
        ind = clean(t.get("CreditDebitIndicator")).lower()
        try:
            v = abs(parse_amount(a.get("Amount")) or ZERO)
        except AmountError as e:
            out.append(_entry(n, d, "", None, ZERO, cur, [M.issue(M.ERROR, f"Item {n}: {e}", n, "amount")])); continue
        if ind not in ("credit", "debit"):
            iss.append(M.issue(M.ERROR, f"Item {n}: CreditDebitIndicator must be Credit or Debit.", n))
        out.append(_entry(n, d, clean(t.get("TransactionInformation")), clean(t.get("TransactionId")) or None, v if ind == "credit" else -v, cur, iss))
    return out


_PARSERS: Dict[str, Callable] = {"PAYSTACK": _paystack, "FLUTTERWAVE": _flutterwave, "STRIPE": _stripe, "PLAID": _plaid, "OPEN_BANKING_UK": _open_banking}


def stage_provider_json(content: bytes, source: dict, options: dict) -> dict:
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise UnsupportedFileError(f"This is not valid JSON: {e}")
    provider = options.get("provider") or detect_provider(payload)
    if provider is None:
        raise IngestionError("I could not tell which provider this JSON came from. Supported: " + "; ".join(PROVIDERS.values()) + ". Choose the provider to force it.")
    if provider not in _PARSERS:
        raise IngestionError(f"Unknown provider {provider!r}.")
    if not isinstance(payload, dict):
        raise IngestionError("The JSON must be the provider's response object.")
    batch = M.new_batch("BANK_TRANSACTIONS", source, {k: v for k, v in options.items() if k in ("provider", "flip")})
    batch["source"].update({"format": "JSON", "provider": provider, "provider_label": PROVIDERS[provider]})
    entries = _PARSERS[provider](payload)
    if options.get("flip"):
        for e in entries:
            e["money_in"], e["money_out"] = e["money_out"], e["money_in"]
    batch["mapping"] = {"provider": PROVIDERS[provider]}
    out = finish_bank_batch(batch, entries, period=options.get("period"), expected_currency=options.get("currency"))
    out["limits"] = [f"Payload shape follows {PROVIDERS[provider]} documentation and has not been checked against a live account.",
                     "This reads a saved response. ASAVEXA is not connected to the provider, and no credentials are stored.",
                     "Fees are listed as separate money-out lines so the books can show them as an expense."]
    return out


# ------------------------------------------------------------------ webhook signature checks (building blocks)
def verify_webhook(provider: str, secret: str, headers: Dict[str, str], body: bytes, now: Optional[float] = None, tolerance: int = 300) -> bool:
    """True only if the provider's signature on `body` matches `secret`. Constant-time compares; replay window for Stripe."""
    h = {k.lower(): v for k, v in headers.items()}
    if not secret:
        return False
    if provider == "PAYSTACK":
        sig = h.get("x-paystack-signature", "")
        return hmac.compare_digest(hmac.new(secret.encode(), body, hashlib.sha512).hexdigest(), sig)
    if provider == "FLUTTERWAVE":
        return hmac.compare_digest(secret, h.get("verif-hash", ""))
    if provider == "STRIPE":
        parts = dict(kv.split("=", 1) for kv in h.get("stripe-signature", "").split(",") if "=" in kv)
        try:
            t = int(parts["t"])
        except (KeyError, ValueError):
            return False
        if abs((now if now is not None else time.time()) - t) > tolerance:
            return False
        good = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
        return any(hmac.compare_digest(good, v) for k, v in [kv.split("=", 1) for kv in h.get("stripe-signature", "").split(",") if kv.startswith("v1=")])
    raise IngestionError(f"No webhook rule for {provider!r}.")
