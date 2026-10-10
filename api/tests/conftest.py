"""PostgreSQL fixtures.

Integration tests need a disposable database. Set TEST_DATABASE_URL to one whose
name ends in `_test`, or install `pgserver` and a throwaway local server is used.
Every test gets a freshly migrated `health` schema.
"""
import os
import shutil
import tempfile
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg.conninfo import conninfo_to_dict

API_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def database_url():
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        name = conninfo_to_dict(url).get("dbname", "")
        if not name.endswith("_test"):
            pytest.fail("TEST_DATABASE_URL must point to a disposable database whose name ends in _test")
        yield url
        return
    pgserver = pytest.importorskip("pgserver", reason="set TEST_DATABASE_URL or install pgserver")
    data_dir = tempfile.mkdtemp(prefix="lifey-pg-")
    server = pgserver.get_server(data_dir, cleanup_mode="stop")
    base = server.get_uri()
    with psycopg.connect(base, autocommit=True) as conn:
        conn.execute("CREATE DATABASE lifey_test")
    yield base.rsplit("/", 1)[0] + "/lifey_test"
    try:
        server.cleanup()
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)


def migrate(url: str) -> None:
    os.environ["DATABASE_URL"] = url
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    command.upgrade(cfg, "head")


@pytest.fixture
def pg(database_url, monkeypatch):
    with psycopg.connect(database_url, autocommit=True) as admin:
        admin.execute("DROP SCHEMA IF EXISTS health CASCADE")
        admin.execute("DROP SCHEMA IF EXISTS auth CASCADE")
        admin.execute("DROP SCHEMA IF EXISTS journal CASCADE")
        admin.execute("DROP TABLE IF EXISTS public.alembic_version")
    migrate(database_url)
    monkeypatch.setenv("DATABASE_URL", database_url)
    with psycopg.connect(database_url) as conn:
        yield conn
        conn.rollback()
