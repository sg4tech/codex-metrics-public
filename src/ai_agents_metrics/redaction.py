"""Secret redaction helpers for observability logs and audit payloads."""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED_TEXT = "[REDACTED]"
_URL_USERINFO_PATTERN = re.compile(r"(https?://)[^\s/:]+:[^\s/@]+@")

_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "private_key",
    "client_secret",
    "refresh_token",
    "access_token",
)

_TEXT_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----", re.DOTALL),
        REDACTED_TEXT,
    ),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._-]{10,}\b"), REDACTED_TEXT),
    (re.compile(r"(?i)\bAuthorization:\s*Bearer\s+[A-Za-z0-9._-]{10,}\b"), REDACTED_TEXT),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), REDACTED_TEXT),
    (re.compile(r"\bASIA[0-9A-Z]{16}\b"), REDACTED_TEXT),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"), REDACTED_TEXT),
    (re.compile(r"\bsk-[A-Za-z0-9._-]{20,}\b"), REDACTED_TEXT),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), REDACTED_TEXT),
)


def redact_text(text: str) -> str:
    redacted = _URL_USERINFO_PATTERN.sub(r"\1[REDACTED]@", text)
    for pattern, replacement in _TEXT_REDACTIONS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(key):
                redacted[key] = REDACTED_TEXT
            else:
                redacted[key] = redact_value(item)
        return redacted
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [redact_value(item) for item in value]
    return value


def _is_sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)
