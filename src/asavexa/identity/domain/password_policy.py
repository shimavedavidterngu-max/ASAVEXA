"""
The ONE password policy, used for sign-up, password reset and (through hash_password) every place a password is stored.
The front end mirrors these numbers in frontend/src/lib/passwords.js; tests/test_password_recovery.py checks the two agree.

Policy (documented, and shown to the person beneath the password field):
  - 8 to 128 characters (counted as Unicode characters)
  - at least one letter (any alphabet) and at least one digit (0-9)
  - spaces and symbols are allowed and are kept exactly as typed: a password is NEVER trimmed or altered
  - not one of a short list of the most common passwords

Note for the operator: the earlier build required 15 characters (NIST SP 800-63B rev 4, for a password used alone). The product
owner chose 8 + letter + digit for sign-up. Existing accounts are unaffected (they can still sign in); the policy applies only
when a password is created or changed. The common-password check and the sign-in lockout are what keep this length workable.
"""
from __future__ import annotations

from typing import List

MIN_LENGTH = 8
MAX_LENGTH = 128

REQUIREMENTS = [
    f"At least {MIN_LENGTH} characters",
    "At least one letter",
    "At least one number",
]

# Lower-case. A small, deliberately short list of passwords that satisfy the rules above but are among the most guessed.
COMMON = frozenset("""
password1 password12 password123 password1234 password12345 passw0rd p@ssw0rd p@ssword1 qwerty123 qwerty1234 qwertyuiop1
1q2w3e4r 1qaz2wsx abc12345 abcd1234 abcd12345 admin123 admin1234 administrator1 welcome1 welcome123 letmein123 iloveyou1
iloveyou123 monkey123 dragon123 football1 baseball1 sunshine1 princess1 trustno1 changeme1 changeme123 asavexa123 asavexa1
12345678a a12345678 123456789a a123456789 11111111a 1234567a8
""".split())


def problems(password) -> List[str]:
    """Every rule the password breaks, in plain words. Empty list means it is acceptable."""
    if not isinstance(password, str) or password == "":
        return ["Enter a password."]
    out: List[str] = []
    n = len(password)
    if n < MIN_LENGTH:
        out.append(f"Use at least {MIN_LENGTH} characters.")
    if n > MAX_LENGTH:
        out.append(f"Use no more than {MAX_LENGTH} characters.")
    if not any(c.isalpha() for c in password):
        out.append("Include at least one letter.")
    if not any("0" <= c <= "9" for c in password):
        out.append("Include at least one number.")
    if password.lower() in COMMON:
        out.append("That password is too common. Choose something less guessable.")
    return out


def check(password) -> None:
    """Raises WeakPasswordError with a readable message when the password breaks the policy."""
    from .errors import WeakPasswordError
    p = problems(password)
    if p:
        raise WeakPasswordError(" ".join(p))
