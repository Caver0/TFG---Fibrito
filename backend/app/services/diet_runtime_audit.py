"""Structured runtime audit logging for diet generation and regeneration flows."""
from __future__ import annotations

import json
import logging
import os
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel

_audit_context: ContextVar[dict[str, Any] | None] = ContextVar("diet_runtime_audit_context", default=None)
_audit_logger = logging.getLogger("fibrito.diet_runtime_audit")


def _ensure_audit_logger() -> logging.Logger:
    if not _audit_logger.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(logging.Formatter("%(message)s"))
        _audit_logger.addHandler(stream_handler)
        _audit_logger.setLevel(logging.INFO)
        _audit_logger.propagate = False
    return _audit_logger


def _audit_log_path() -> Path:
    configured_path = os.getenv("FIBRITO_DIET_AUDIT_LOG_PATH", "").strip()
    if configured_path:
        return Path(configured_path)
    return Path(__file__).resolve().parents[2] / "runtime_logs" / "diet_runtime_audit.jsonl"


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {
            str(key): _to_jsonable(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_to_jsonable(item) for item in value]
    return value


def new_audit_id(prefix: str) -> str:
    normalized_prefix = prefix.strip().replace(" ", "_") or "diet"
    return f"{normalized_prefix}_{uuid.uuid4().hex[:12]}"


@contextmanager
def runtime_audit_context(*, audit_id: str, endpoint: str, user_id: str | None = None) -> Iterator[str]:
    context_payload = {
        "audit_id": audit_id,
        "endpoint": endpoint,
        "user_id": user_id,
    }
    token = _audit_context.set(context_payload)
    try:
        yield audit_id
    finally:
        _audit_context.reset(token)


def get_runtime_audit_context() -> dict[str, Any]:
    return dict(_audit_context.get() or {})


def emit_runtime_audit(event: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    logger = _ensure_audit_logger()
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": event,
        **get_runtime_audit_context(),
        **_to_jsonable(payload or {}),
    }
    serialized_entry = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    logger.info(serialized_entry)

    log_path = _audit_log_path()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(serialized_entry + "\n")
    except OSError:
        # Best-effort file logging only; stdout logging remains the source of truth.
        pass
    return entry
