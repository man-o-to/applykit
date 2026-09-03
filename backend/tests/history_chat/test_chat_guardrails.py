import asyncio
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.role_match.models  # noqa: F401 - registers role_match tables on Base
from app.models import Base, CvChatMessage, GeneratedCV
from app.routes import history_chat
from app.schemas import ChatMessageRequest

SNAPSHOT = json.dumps({"name": "Jane", "email": "jane@example.com", "summary": "s"})


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _cv(db) -> GeneratedCV:
    entry = GeneratedCV(enhanced=0, profile_snapshot=SNAPSHOT)
    db.add(entry)
    db.commit()
    return entry


async def _drain(stream):
    events = []
    async for event in stream:
        events.append(event)
    return events


def _run_turn(db, session_id, content="hi"):
    stream = history_chat.stream_cv_chat_turn(
        session_id=session_id,
        req=ChatMessageRequest(content=content),
        db=db,
        llm=("openai/test-model", "test-key"),
    )
    return asyncio.run(_drain(stream))


def test_turn_cap_allows_up_to_the_limit_then_rejects_the_next_one(monkeypatch):
    db = make_session()
    entry = _cv(db)
    response = history_chat.create_cv_chat(entry_id=entry.id, db=db)

    async def fake_stream_llm(*args, **kwargs):
        yield "ok"

    monkeypatch.setattr(history_chat, "stream_llm", fake_stream_llm)

    for turn in range(history_chat.MAX_TURNS_PER_SESSION):
        _run_turn(db, response.id, content=f"turn {turn}")

    session = history_chat.get_cv_chat_session(db, response.id)
    assert session.turn_count == history_chat.MAX_TURNS_PER_SESSION

    called_after_cap = False

    async def should_not_run(*args, **kwargs):
        nonlocal called_after_cap
        called_after_cap = True
        yield "unreachable"

    monkeypatch.setattr(history_chat, "stream_llm", should_not_run)

    # Guardrail failures are yielded as an `error` event rather than raised
    # directly - see the comment in history_chat.py's turn-stream routes.
    events = _run_turn(db, response.id, content="one too many")
    assert events[-1].event == "error"
    assert called_after_cap is False
    assert history_chat.get_cv_chat_session(db, response.id).turn_count == history_chat.MAX_TURNS_PER_SESSION


def test_the_19th_and_20th_turns_succeed_right_up_to_the_boundary(monkeypatch):
    db = make_session()
    entry = _cv(db)
    response = history_chat.create_cv_chat(entry_id=entry.id, db=db)

    async def fake_stream_llm(*args, **kwargs):
        yield "ok"

    monkeypatch.setattr(history_chat, "stream_llm", fake_stream_llm)

    for turn in range(history_chat.MAX_TURNS_PER_SESSION - 2):
        _run_turn(db, response.id, content=f"turn {turn}")
    assert history_chat.get_cv_chat_session(db, response.id).turn_count == history_chat.MAX_TURNS_PER_SESSION - 2

    _run_turn(db, response.id, content="19th")  # does not raise
    assert history_chat.get_cv_chat_session(db, response.id).turn_count == history_chat.MAX_TURNS_PER_SESSION - 1

    _run_turn(db, response.id, content="20th")  # does not raise
    assert history_chat.get_cv_chat_session(db, response.id).turn_count == history_chat.MAX_TURNS_PER_SESSION


def test_sliding_window_drops_the_oldest_message_once_the_window_is_exceeded(monkeypatch):
    db = make_session()
    entry = _cv(db)
    response = history_chat.create_cv_chat(entry_id=entry.id, db=db)

    # Seed 9 stored messages directly - one more than CHAT_HISTORY_WINDOW (8).
    for i in range(1, 10):
        db.add(
            CvChatMessage(
                session_id=response.id,
                role="user" if i % 2 else "assistant",
                content=f"message {i}",
            )
        )
    db.commit()

    captured: dict = {}

    async def fake_stream_llm(*args, **kwargs):
        captured["history"] = kwargs.get("history")
        yield "ok"

    monkeypatch.setattr(history_chat, "stream_llm", fake_stream_llm)

    _run_turn(db, response.id, content="the 10th message, sent now")

    history = captured["history"]
    assert len(history) == history_chat.CHAT_HISTORY_WINDOW
    contents = [m["content"] for m in history]
    assert "message 1" not in contents  # oldest dropped
    assert contents[0] == "message 2"
    assert contents[-1] == "message 9"
