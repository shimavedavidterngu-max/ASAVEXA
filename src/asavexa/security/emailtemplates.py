"""Every account email ASAVEXA sends, in one place: a clear subject, a mobile-friendly HTML body (single column, inline styles, large text),
and a plain-text alternative that says the same thing. Nothing here ever includes a password, a session token or a database identifier.

Templates: account created, verify your email, password recovery code, password changed, security alert.
The HTML is built from escaped text only, so a value that contains markup can never become markup.
"""
from __future__ import annotations

import html as _html
from dataclasses import dataclass
from typing import Optional

BRAND = "ASAVEXA"
TAGLINE = "Don't just report the number. Prove it."


@dataclass(frozen=True)
class Email:
    subject: str
    text: str
    html: str


def _e(value) -> str:
    return _html.escape(str(value), quote=True)


def _shell(preheader: str, body_html: str, footer_html: str) -> str:
    """One responsive, accessible layout for every email: 600px max, system fonts, high contrast, real <h1>, a hidden preheader."""
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{BRAND}</title></head>"
        "<body style='margin:0;padding:0;background:#eef2f6;'>"
        f"<div style='display:none;max-height:0;overflow:hidden;opacity:0;color:transparent'>{_e(preheader)}</div>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='background:#eef2f6;'><tr><td align='center' style='padding:24px 12px;'>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='max-width:600px;background:#ffffff;border-radius:10px;'>"
        "<tr><td style='padding:28px 28px 8px 28px;font-family:Georgia,\"Times New Roman\",serif;font-size:24px;color:#0b1b2b;'>"
        f"{BRAND}<div style='font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#4a5a6a;margin-top:2px;'>{_e(TAGLINE)}</div></td></tr>"
        f"<tr><td style='padding:8px 28px 8px 28px;font-family:Arial,Helvetica,sans-serif;font-size:16px;line-height:1.55;color:#0b1b2b;'>{body_html}</td></tr>"
        f"<tr><td style='padding:16px 28px 28px 28px;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:1.5;color:#4a5a6a;'>{footer_html}</td></tr>"
        "</table></td></tr></table></body></html>"
    )


def _code_block(code: str) -> str:
    return (f"<p style='margin:20px 0;'><span style='display:inline-block;font-family:Consolas,Menlo,monospace;font-size:34px;letter-spacing:10px;"
            f"font-weight:bold;color:#0b1b2b;background:#eef2f6;border-radius:8px;padding:12px 18px;'>{_e(code)}</span></p>")


def _button(url: str, label: str) -> str:
    return (f"<p style='margin:24px 0;'><a href='{_e(url)}' style='background:#0f6b63;color:#ffffff;text-decoration:none;font-weight:bold;"
            f"padding:13px 22px;border-radius:7px;display:inline-block;'>{_e(label)}</a></p>")


def _support(support_email: Optional[str]) -> tuple[str, str]:
    if not support_email:
        return "", ""
    return (f"\n\nNeed help? Contact {support_email}.",
            f"<br>Need help? Contact <a href='mailto:{_e(support_email)}' style='color:#0f6b63;'>{_e(support_email)}</a>.")


SECURITY_NOTE_TEXT = "ASAVEXA will never ask you for your password, or for a verification code, by email, phone or chat."
SECURITY_NOTE_HTML = "ASAVEXA will never ask you for your password, or for a verification code, by email, phone or chat."


# ---------------------------------------------------------------------------------------------------------------- the five emails
def account_created(app_url: Optional[str] = None, support_email: Optional[str] = None, verification_pending: bool = True) -> Email:
    """Welcome: the account exists. Says what is left to do (confirm the email) and gives basic security advice."""
    subject = "Welcome to ASAVEXA — Your Account Has Been Created Successfully"
    next_step = ("One step is left: confirm that this email address is yours. We sent a separate email with a 6-digit verification code. "
                 "Enter it on the ASAVEXA verification screen. The code expires in 10 minutes, and you can ask for a new one there." if verification_pending
                 else "Your email address is already confirmed, so there is nothing else to do.")
    advice = ["Use a password you do not use anywhere else.", "Never share your password or a verification code with anyone.",
              "If you did not create this account, ignore this email or tell us."]
    s_text, s_html = _support(support_email)
    link_text = f"\n\nOpen ASAVEXA: {app_url}" if app_url else ""
    text = (f"Welcome to ASAVEXA.\n\nYour ASAVEXA account was created successfully for this email address.\n\n{next_step}\n\n"
            "Staying safe:\n" + "\n".join(f"- {a}" for a in advice) + link_text + s_text + f"\n\n{SECURITY_NOTE_TEXT}")
    body = ("<h1 style='font-size:22px;margin:12px 0 8px;'>Your account has been created</h1>"
            "<p>Welcome to ASAVEXA. Your account was created successfully for this email address.</p>"
            f"<p>{_e(next_step)}</p>"
            + (_button(app_url, "Open ASAVEXA") if app_url else "")
            + "<p style='margin-bottom:4px;'><strong>Staying safe</strong></p><ul style='margin-top:4px;padding-left:20px;'>"
            + "".join(f"<li>{_e(a)}</li>" for a in advice) + "</ul>")
    return Email(subject, text, _shell("Your ASAVEXA account has been created.", body, _e(SECURITY_NOTE_HTML) + s_html))


def verify_email(code: str, minutes: int) -> Email:
    subject = "Verify your email address for ASAVEXA"
    text = (f"Your ASAVEXA email verification code is {code}\n\nIt expires in {minutes} minutes and can be used once.\n\n"
            "Enter it on the ASAVEXA verification screen to confirm that this email address is yours.\n\n"
            "If you did not create an ASAVEXA account, ignore this email: nothing will happen.\n\n" + SECURITY_NOTE_TEXT)
    body = ("<h1 style='font-size:22px;margin:12px 0 8px;'>Verify your email address</h1>"
            "<p>Enter this code on the ASAVEXA verification screen to confirm that this email address is yours.</p>"
            + _code_block(code) + f"<p>It expires in <strong>{int(minutes)} minutes</strong> and can be used once.</p>"
            "<p>If you did not create an ASAVEXA account, ignore this email: nothing will happen.</p>")
    return Email(subject, text, _shell(f"Your ASAVEXA verification code expires in {int(minutes)} minutes.", body, _e(SECURITY_NOTE_HTML)))


def recovery_code(code: str, minutes: int) -> Email:
    subject = "Your ASAVEXA verification code"
    text = (f"Your ASAVEXA verification code is {code}\n\nIt expires in {minutes} minutes and can be used once.\n\n"
            "You are receiving this because someone asked to reset the password for the ASAVEXA account that uses this email address. "
            "If that was you, enter the code on the password reset page. If it was not, you can ignore this email: your password has not changed.\n\n"
            + SECURITY_NOTE_TEXT)
    body = ("<h1 style='font-size:22px;margin:12px 0 8px;'>Reset your password</h1>"
            "<p>Your verification code is</p>" + _code_block(code) + f"<p>It expires in <strong>{int(minutes)} minutes</strong> and can be used once.</p>"
            "<p>You are receiving this because someone asked to reset the password for the ASAVEXA account that uses this email address. "
            "If that was you, enter the code on the password reset page. If it was not, ignore this email: your password has not changed.</p>")
    return Email(subject, text, _shell(f"Your ASAVEXA password reset code expires in {int(minutes)} minutes.", body, _e(SECURITY_NOTE_HTML)))


def password_changed(support_email: Optional[str] = None) -> Email:
    subject = "Your ASAVEXA password was changed"
    s_text, s_html = _support(support_email)
    text = ("The password for your ASAVEXA account was just changed, and you were signed out everywhere.\n\n"
            "If you did this, no action is needed. If you did not, reset your password again straight away and tell your organisation's administrator." + s_text)
    body = ("<h1 style='font-size:22px;margin:12px 0 8px;'>Your password was changed</h1>"
            "<p>The password for your ASAVEXA account was just changed, and you were signed out everywhere.</p>"
            "<p>If you did this, no action is needed. If you did not, reset your password again straight away and tell your organisation's administrator.</p>")
    return Email(subject, text, _shell("Your ASAVEXA password was changed.", body, _e(SECURITY_NOTE_HTML) + s_html))


def security_alert(title: str, detail: str, support_email: Optional[str] = None) -> Email:
    """Optional alert for an important account change (for example: sign-in method changed). `detail` is plain text, escaped here."""
    subject = f"ASAVEXA security alert: {title}"
    s_text, s_html = _support(support_email)
    text = f"{title}\n\n{detail}\n\nIf this was not you, reset your password now and tell your organisation's administrator." + s_text
    body = (f"<h1 style='font-size:22px;margin:12px 0 8px;'>{_e(title)}</h1><p>{_e(detail)}</p>"
            "<p>If this was not you, reset your password now and tell your organisation's administrator.</p>")
    return Email(subject, text, _shell(title, body, _e(SECURITY_NOTE_HTML) + s_html))
