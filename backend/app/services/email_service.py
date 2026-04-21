"""SMTP email delivery helpers."""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.core.config import get_settings


class EmailConfigurationError(RuntimeError):
    """Raised when SMTP settings are incomplete or invalid."""


class EmailDeliveryError(RuntimeError):
    """Raised when the SMTP server rejects or cannot deliver the email."""


def validate_email_delivery_settings() -> None:
    settings = get_settings()
    missing_fields: list[str] = []

    if not settings.smtp_host.strip():
        missing_fields.append("SMTP_HOST")
    if not settings.smtp_from_email.strip():
        missing_fields.append("SMTP_FROM_EMAIL")
    if bool(settings.smtp_username.strip()) ^ bool(settings.smtp_password.strip()):
        missing_fields.append("SMTP_USERNAME and SMTP_PASSWORD")
    if settings.smtp_use_tls and settings.smtp_use_ssl:
        raise EmailConfigurationError("SMTP_USE_TLS and SMTP_USE_SSL cannot both be enabled")
    if missing_fields:
        raise EmailConfigurationError(
            "SMTP is not fully configured. Missing or invalid settings: "
            + ", ".join(missing_fields)
        )


def send_email(*, to_email: str, subject: str, text_body: str, html_body: str | None = None) -> None:
    validate_email_delivery_settings()
    settings = get_settings()

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = (
        f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
        if settings.smtp_from_name.strip()
        else settings.smtp_from_email
    )
    message["To"] = to_email
    message.set_content(text_body)

    if html_body:
        message.add_alternative(html_body, subtype="html")

    try:
        smtp_client: smtplib.SMTP
        if settings.smtp_use_ssl:
            smtp_client = smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
            )
        else:
            smtp_client = smtplib.SMTP(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
            )

        with smtp_client as server:
            server.ehlo()
            if settings.smtp_use_tls:
                server.starttls()
                server.ehlo()
            if settings.smtp_username.strip():
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
    except EmailConfigurationError:
        raise
    except Exception as exc:
        raise EmailDeliveryError("Failed to send email using the configured SMTP server") from exc
