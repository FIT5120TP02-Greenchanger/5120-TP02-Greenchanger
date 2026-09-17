"""Shared test fixtures: a fake DB connection standing in for the real Aurora pool."""

from __future__ import annotations

import pytest

from app.db import get_db
from app.main import app


class FakeCursor:
    """Minimal stand-in for a psycopg cursor.

    Each execute() call consumes the next queued resultset; fetchall()/fetchone()
    read from whatever resultset the most recent execute() queued up.
    """

    def __init__(self, resultsets: list[list[dict]]):
        self._resultsets = list(resultsets)
        self._current: list[dict] = []

    def execute(self, *args, **kwargs):
        self._current = self._resultsets.pop(0) if self._resultsets else []

    def fetchall(self):
        return self._current

    def fetchone(self):
        return self._current[0] if self._current else None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConnection:
    def __init__(self, resultsets: list[list[dict]]):
        self._resultsets = resultsets

    def cursor(self):
        return FakeCursor(self._resultsets)


@pytest.fixture
def override_db():
    """override_db([[row, row], [row]]) -- one list per expected execute() call."""

    def _apply(resultsets: list[list[dict]]):
        def _fake_get_db():
            yield FakeConnection(resultsets)

        app.dependency_overrides[get_db] = _fake_get_db

    yield _apply
    app.dependency_overrides.clear()
