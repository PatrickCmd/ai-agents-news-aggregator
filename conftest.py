"""Root pytest config — exposes `tests/integration/conftest.py` fixtures globally.

Pytest only walks UP from a test file looking for `conftest.py`. The
testcontainers-postgres fixtures (`pg_container`, `session`,
`db_session_factory`) live at `tests/integration/conftest.py`, which is a
sibling tree to `services/<svc>/.../tests/integration/`. To make those
fixtures available to service-local integration tests too, we register the
sibling conftest as a plugin from the repo root.

Trade-off: the testcontainers module imports at test session start
(harmless — it doesn't spin up Docker until a fixture requests it).
"""

pytest_plugins = ["tests.integration.conftest"]
