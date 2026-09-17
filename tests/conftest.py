"""Shared test fixtures: isolated SQLite database before core modules load."""

import os
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="faceshield_test_")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP_DIR}/test.db"
os.environ["AGENT_ENABLED"] = "false"

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_database():
    """Give every test clean tables (idempotent schema reset)."""
    import asyncio

    from core import database
    from core.models import Base

    async def reset():
        async with database.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        # Re-seed default settings row after dropping tables.
        await database.init_db()

    asyncio.run(reset())
    yield


@pytest.fixture(autouse=True)
def _clean_global_cache():
    """Reset the module-level face cache between tests."""
    from core.face_cache import face_cache
    from core.face_cache import FaceCache

    fresh = FaceCache()
    face_cache._lock = fresh._lock
    face_cache._matrix = fresh._matrix
    face_cache._ids = fresh._ids
    face_cache._names = fresh._names
    face_cache._index = fresh._index
    yield
