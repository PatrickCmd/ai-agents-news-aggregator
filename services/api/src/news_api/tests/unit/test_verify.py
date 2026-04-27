"""Unit tests for ClerkClaims and InvalidKid."""

import pytest
from pydantic import ValidationError

from news_api.auth.verify import ClerkClaims, InvalidKid


def test_clerk_claims_minimum_required():
    claims = ClerkClaims.model_validate(
        {
            "sub": "user_abc",
            "email": "alice@example.com",
            "name": "Alice Smith",
            "exp": 1_777_777_777,
            "iat": 1_777_777_000,
            "iss": "https://test.clerk.dev",
        }
    )
    assert claims.sub == "user_abc"
    assert claims.email == "alice@example.com"
    assert claims.name == "Alice Smith"
    assert claims.azp is None  # optional


def test_clerk_claims_rejects_invalid_email():
    with pytest.raises(ValidationError):
        ClerkClaims.model_validate(
            {
                "sub": "user_abc",
                "email": "not-an-email",
                "name": "Alice",
                "exp": 1_777_777_777,
                "iat": 1_777_777_000,
                "iss": "https://test.clerk.dev",
            }
        )


def test_invalid_kid_is_exception_subclass():
    assert issubclass(InvalidKid, Exception)
    raised = InvalidKid("kid 'foo' not in JWKS")
    assert "foo" in str(raised)
