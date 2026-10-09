"""Prints values for the two environment variables the platform needs.  Run:  python -m asavexa.security.keygen

Uses only the Python standard library, so it runs on any computer with Python and needs nothing installed."""
import base64
import datetime
import secrets

if __name__ == "__main__":
    kid = datetime.date.today().strftime("%Y-%m")
    key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    print(f"ASAVEXA_KEYS={kid}:{key}")
    print(f"ASAVEXA_CURRENT_KEY={kid}")
    print("\nStore these in your host's secret settings (never in git). To rotate: add a NEW id:key to ASAVEXA_KEYS, keep the old one,"
          "\nthen change ASAVEXA_CURRENT_KEY. Keep old keys until the rotation job reports nothing left on them.")
