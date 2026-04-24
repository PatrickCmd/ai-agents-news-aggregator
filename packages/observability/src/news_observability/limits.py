"""Size caps for audit logs and LLM responses."""

from __future__ import annotations

MAX_AUDIT_INPUT_CHARS: int = 2_000
MAX_AUDIT_OUTPUT_CHARS: int = 2_000
MAX_LLM_RESPONSE_CHARS: int = 200_000


def truncate_for_audit(s: str, limit: int) -> str:
    """Truncate to *limit* characters, appending '…' when truncation happened."""
    if limit <= 0:
        return ""
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"
