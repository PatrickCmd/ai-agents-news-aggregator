"""Prompt-injection sanitizer. Call before any user-supplied text reaches an LLM."""

from __future__ import annotations

import re


class PromptInjectionError(ValueError):
    """Raised when input contains a hard-blocked injection pattern."""


# Hard-block: patterns we refuse outright.
_HARD_BLOCK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"<\|im_end\|>", re.IGNORECASE),
    re.compile(r"<\|system\|>", re.IGNORECASE),
    re.compile(r"```system", re.IGNORECASE),
)

# Soft-strip: phrases we redact silently.
_SOFT_STRIP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"ignore (all |any )?(previous|above|prior) (instructions?|prompts?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"disregard (all |any )?(previous|above|prior) (instructions?|prompts?)",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*(system|user|assistant|developer)\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"you are (now )?(root|admin|god)", re.IGNORECASE),
)


def sanitize_prompt_input(text: str) -> str:
    """Return cleaned text; raise PromptInjectionError on hard-block patterns."""
    for p in _HARD_BLOCK_PATTERNS:
        if p.search(text):
            raise PromptInjectionError(f"Hard-block pattern matched: {p.pattern}")

    cleaned = text
    for p in _SOFT_STRIP_PATTERNS:
        cleaned = p.sub("[REDACTED]", cleaned)
    return cleaned
