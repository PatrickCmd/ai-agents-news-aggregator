import pytest
from pydantic import BaseModel

from news_observability.validators import StructuredOutputError, validate_structured_output


class _M(BaseModel):
    x: int


def test_accepts_valid_dict():
    m = validate_structured_output(_M, {"x": 1})
    assert m.x == 1


def test_accepts_valid_json_string():
    m = validate_structured_output(_M, '{"x": 2}')
    assert m.x == 2


def test_rejects_invalid_with_structured_output_error():
    with pytest.raises(StructuredOutputError):
        validate_structured_output(_M, {"x": "nope"})


def test_rejects_malformed_json_string():
    with pytest.raises(StructuredOutputError):
        validate_structured_output(_M, "not json")
