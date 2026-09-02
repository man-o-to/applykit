import os
import sqlite3
import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

BACKEND_ROOT = Path(__file__).parents[1]
REVISION = "7ded17ffc82f"
DOWN_REVISION = "f24b8ab225da"


@pytest.fixture(autouse=True)
def _restore_database_url_env():
    original = os.environ.get("DATABASE_URL")
    yield
    if original is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = original


def _alembic_config(db_path: str) -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    return cfg


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


NEW_COLUMNS = {
    "parent_version_id",
    "superseded_by_id",
    "edit_source",
    "edit_instruction",
    "edit_target_excerpt",
}


def test_migration_upgrade_adds_columns_without_losing_existing_rows():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        cfg = _alembic_config(db_path)

        # Get to the revision right before this one, insert real rows through
        # the actual prior schema, then upgrade just this one migration.
        command.upgrade(cfg, DOWN_REVISION)
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO generated_cv (id, created_at, enhanced, profile_snapshot) "
            "VALUES (1, '2026-01-01', 0, '{}')"
        )
        conn.execute(
            "INSERT INTO generated_cover_letter "
            "(id, created_at, job_description, cover_letter_text, tone) "
            "VALUES (1, '2026-01-01', 'Job desc', 'Dear hiring manager', 'professional')"
        )
        conn.commit()
        conn.close()

        command.upgrade(cfg, REVISION)

        conn = sqlite3.connect(db_path)
        for table in ("generated_cv", "generated_cover_letter"):
            assert NEW_COLUMNS <= _columns(conn, table), table

        cv_row = conn.execute(
            "SELECT profile_snapshot, parent_version_id, superseded_by_id FROM generated_cv WHERE id = 1"
        ).fetchone()
        assert cv_row == ("{}", None, None)

        cl_row = conn.execute(
            "SELECT cover_letter_text, parent_version_id FROM generated_cover_letter WHERE id = 1"
        ).fetchone()
        assert cl_row == ("Dear hiring manager", None)
        conn.close()


def test_migration_downgrade_removes_columns_cleanly():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        cfg = _alembic_config(db_path)

        command.upgrade(cfg, REVISION)
        conn = sqlite3.connect(db_path)
        for table in ("generated_cv", "generated_cover_letter"):
            assert NEW_COLUMNS <= _columns(conn, table)
        conn.close()

        command.downgrade(cfg, DOWN_REVISION)

        conn = sqlite3.connect(db_path)
        for table in ("generated_cv", "generated_cover_letter"):
            assert NEW_COLUMNS.isdisjoint(_columns(conn, table)), table
        conn.close()
