"""Structured-output validator for LLM responses."""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from news_observability.logging import get_logger

_log = get_logger("validators")

M = TypeVar("M", bound=BaseModel)


class StructuredOutputError(ValueError):
    """Raised when an LLM response fails Pydantic validation."""


def validate_structured_output(model: type[M], raw: str | dict[str, object]) -> M:
    """Validate *raw* against *model*. Accepts a dict or a JSON string.

    Logs failures and raises StructuredOutputError so callers can trigger
    retry_llm / audit flows consistently.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as e:
            _log.error("structured output not JSON: {}", e)
            raise StructuredOutputError(f"not JSON: {e}") from e
    try:
        return model.model_validate(raw)
    except ValidationError as e:
        _log.error("structured output failed validation: {}", e.errors())
        raise StructuredOutputError(str(e)) from e
