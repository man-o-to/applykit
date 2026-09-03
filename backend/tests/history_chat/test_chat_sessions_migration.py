import os
import sqlite3
import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

BACKEND_ROOT = Path(__file__).parents[2]
REVISION = "a64dce629443"
DOWN_REVISION = "7ded17ffc82f"

NEW_TABLES = {
    "cv_chat_session",
    "cv_chat_message",
    "cover_letter_chat_session",
    "cover_letter_chat_message",
}


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


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_migration_upgrade_adds_chat_tables_without_losing_existing_rows():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        cfg = _alembic_config(db_path)

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
        assert NEW_TABLES <= _tables(conn)
        assert "chat_session_id" in _columns(conn, "generated_cv")
        assert "chat_session_id" in _columns(conn, "generated_cover_letter")

        cv_row = conn.execute(
            "SELECT profile_snapshot, chat_session_id FROM generated_cv WHERE id = 1"
        ).fetchone()
        assert cv_row == ("{}", None)

        cl_row = conn.execute(
            "SELECT cover_letter_text, chat_session_id FROM generated_cover_letter WHERE id = 1"
        ).fetchone()
        assert cl_row == ("Dear hiring manager", None)
        conn.close()


def test_migration_upgrade_lets_chat_rows_reference_generated_documents():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        cfg = _alembic_config(db_path)
        command.upgrade(cfg, REVISION)

        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO generated_cv (id, created_at, enhanced, profile_snapshot) "
            "VALUES (1, '2026-01-01', 0, '{}')"
        )
        conn.execute(
            "INSERT INTO cv_chat_session "
            "(id, cv_root_id, current_cv_id, status, turn_count, created_at, updated_at) "
            "VALUES (1, 1, 1, 'open', 0, '2026-01-01', '2026-01-01')"
        )
        conn.execute(
            "INSERT INTO cv_chat_message (id, session_id, role, content, created_at) "
            "VALUES (1, 1, 'user', 'Make it punchier', '2026-01-01')"
        )
        conn.execute("UPDATE generated_cv SET chat_session_id = 1 WHERE id = 1")
        conn.commit()

        row = conn.execute(
            "SELECT cv_root_id, current_cv_id FROM cv_chat_session WHERE id = 1"
        ).fetchone()
        assert row == (1, 1)
        message_row = conn.execute(
            "SELECT session_id, role, content FROM cv_chat_message WHERE id = 1"
        ).fetchone()
        assert message_row == (1, "user", "Make it punchier")
        assert conn.execute(
            "SELECT chat_session_id FROM generated_cv WHERE id = 1"
        ).fetchone() == (1,)
        conn.close()


def test_migration_downgrade_removes_chat_tables_and_columns_cleanly():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        cfg = _alembic_config(db_path)

        command.upgrade(cfg, REVISION)
        conn = sqlite3.connect(db_path)
        assert NEW_TABLES <= _tables(conn)
        conn.close()

        command.downgrade(cfg, DOWN_REVISION)

        conn = sqlite3.connect(db_path)
        assert NEW_TABLES.isdisjoint(_tables(conn))
        assert "chat_session_id" not in _columns(conn, "generated_cv")
        assert "chat_session_id" not in _columns(conn, "generated_cover_letter")
        conn.close()
