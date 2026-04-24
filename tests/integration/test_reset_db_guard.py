import pytest

from scripts.reset_db import _assert_dev_db


def test_accepts_dev_db():
    _assert_dev_db("postgresql+asyncpg://u:p@h:5432/app_dev")


def test_accepts_local_db():
    _assert_dev_db("postgresql+asyncpg://u:p@h:5432/app_local")


def test_rejects_prod_db():
    with pytest.raises(RuntimeError):
        _assert_dev_db("postgresql+asyncpg://u:p@h:5432/app_prod")
