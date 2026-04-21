"""Password reset helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.core.config import get_settings

INVALID_PASSWORD_RESET_TOKEN_MESSAGE = "Enlace invalido o expirado."


def create_password_reset_token() -> tuple[str, str]:
    token = token_urlsafe(32)
    return token, hash_password_reset_token(token)


def hash_password_reset_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def build_valid_password_reset_query(token_hash: str, *, now: datetime | None = None) -> dict[str, Any]:
    reference_time = now or datetime.now(timezone.utc)
    return {
        "reset_password_token_hash": token_hash,
        "reset_password_expires_at": {"$gt": reference_time},
    }


def get_password_reset_expiration() -> datetime:
    settings = get_settings()
    return datetime.now(timezone.utc) + timedelta(minutes=settings.password_reset_token_expire_minutes)


def build_password_reset_url(token: str) -> str:
    settings = get_settings()
    parsed_url = urlsplit(settings.frontend_url)
    query_params = dict(parse_qsl(parsed_url.query, keep_blank_values=True))
    query_params.update(
        {
            "auth": "reset-password",
            "token": token,
        }
    )
    path = parsed_url.path or "/"
    return urlunsplit(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            path,
            urlencode(query_params),
            parsed_url.fragment,
        )
    )


def build_password_reset_email(name: str, reset_url: str) -> tuple[str, str, str]:
    settings = get_settings()
    expires_in = settings.password_reset_token_expire_minutes
    subject = "Fibrito - restablece tu contrasena"
    text_body = (
        f"Hola {name},\n\n"
        "Hemos recibido una solicitud para restablecer tu contrasena en Fibrito.\n"
        f"Abre este enlace para continuar:\n{reset_url}\n\n"
        f"El enlace caduca en {expires_in} minutos y solo se puede usar una vez.\n"
        "Si no has solicitado este cambio, puedes ignorar este correo.\n"
    )
    html_body = (
        "<html><body style=\"font-family: Arial, sans-serif; color: #111827;\">"
        f"<p>Hola {name},</p>"
        "<p>Hemos recibido una solicitud para restablecer tu contrasena en Fibrito.</p>"
        f"<p><a href=\"{reset_url}\">Restablecer contrasena</a></p>"
        f"<p>El enlace caduca en {expires_in} minutos y solo se puede usar una vez.</p>"
        "<p>Si no has solicitado este cambio, puedes ignorar este correo.</p>"
        "</body></html>"
    )
    return subject, text_body, html_body
