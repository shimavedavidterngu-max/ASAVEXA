"""Inbound webhooks. Today: the email provider's delivery events (Resend, signed with Svix). Nothing here is trusted until its signature is verified."""
from fastapi import APIRouter, Depends, Request

from ...security.context import SecurityContext
from ..deps import get_security

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/email")
async def email_events(request: Request, security: SecurityContext = Depends(get_security)):
    """Delivered / bounced / complained events for messages ASAVEXA sent. Verified against RESEND_WEBHOOK_SECRET; refused (401) otherwise."""
    raw = await request.body()
    result = security.mail_events.handle(raw, request.headers)
    security.commit()
    return result
