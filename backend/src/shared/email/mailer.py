"""Outgoing email — Document Delivery. Stdlib `smtplib` behind a thin
async wrapper: no new heavy dependency for what's fundamentally one
blocking network call per send, run off the event loop via
`asyncio.to_thread` (the same tradeoff FastAPI's own docs recommend for
occasional blocking I/O that isn't worth an async-native client).
"""

from __future__ import annotations

import asyncio
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from src.shared.config.settings import get_settings


class EmailNotConfiguredError(Exception):
    """Raised when SMTP_HOST isn't set — surfaced as a 422 with a clear,
    actionable message rather than silently discarding the send."""


@dataclass(frozen=True)
class EmailAttachment:
    filename: str
    content: bytes
    mime_type: str = "application/pdf"


def _send_sync(message: EmailMessage) -> None:
    settings = get_settings()
    if not settings.smtp_host:
        raise EmailNotConfiguredError(
            "Outgoing email isn't configured for this deployment (SMTP_HOST is unset)."
        )
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username and settings.smtp_password:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


async def send_email(
    *, to: str, subject: str, body: str, attachments: list[EmailAttachment] | None = None
) -> None:
    settings = get_settings()
    if not settings.smtp_host:
        raise EmailNotConfiguredError(
            "Outgoing email isn't configured for this deployment (SMTP_HOST is unset)."
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from_address or settings.smtp_username or "no-reply@localhost"
    message["To"] = to
    message.set_content(body)

    for attachment in attachments or []:
        maintype, _, subtype = attachment.mime_type.partition("/")
        message.add_attachment(
            attachment.content, maintype=maintype or "application", subtype=subtype or "octet-stream",
            filename=attachment.filename,
        )

    await asyncio.to_thread(_send_sync, message)
