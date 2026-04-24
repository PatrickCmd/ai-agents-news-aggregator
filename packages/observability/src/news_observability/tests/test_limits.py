from news_observability.limits import (
    MAX_AUDIT_INPUT_CHARS,
    MAX_AUDIT_OUTPUT_CHARS,
    MAX_LLM_RESPONSE_CHARS,
    truncate_for_audit,
)


def test_constants_are_positive_ints():
    assert MAX_AUDIT_INPUT_CHARS > 0
    assert MAX_AUDIT_OUTPUT_CHARS > 0
    assert MAX_LLM_RESPONSE_CHARS > 0


def test_truncate_shorter_than_limit():
    assert truncate_for_audit("hi", 10) == "hi"


def test_truncate_longer_than_limit():
    out = truncate_for_audit("x" * 100, 10)
    assert len(out) == 10
    assert out.endswith("…")


def test_truncate_zero_limit():
    assert truncate_for_audit("anything", 0) == ""
