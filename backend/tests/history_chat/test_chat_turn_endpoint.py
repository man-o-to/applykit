import asyncio
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.role_match.models  # noqa: F401 - registers role_match tables on Base
from app.exceptions import HistoryEntryNotFoundError, InvalidRequestError
from app.models import Base, CoverLetterChatMessage, CvChatMessage, GeneratedCoverLetter, GeneratedCV
from app.routes import history_chat
from app.schemas import ChatMessageRequest

SNAPSHOT = json.dumps(
    {
        "name": "Jane",
        "email": "jane@example.com",
        "summary": "Old summary.",
        "work_experience": [],
        "education": [],
        "skills": [],
        "projects": [],
        "certifications": [],
    }
)


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _cv(db) -> GeneratedCV:
    entry = GeneratedCV(enhanced=0, profile_snapshot=SNAPSHOT)
    db.add(entry)
    db.commit()
    return entry


def _cl(db) -> GeneratedCoverLetter:
    entry = GeneratedCoverLetter(job_description="desc", cover_letter_text="Dear team,", tone="professional")
    db.add(entry)
    db.commit()
    return entry


async def _drain(stream):
    events = []
    async for event in stream:
        events.append(event)
    return events


def _run_cv_turn(db, session_id, content="Make it punchier"):
    stream = history_chat.stream_cv_chat_turn(
        session_id=session_id,
        req=ChatMessageRequest(content=content),
        db=db,
        llm=("openai/test-model", "test-key"),
    )
    return asyncio.run(_drain(stream))


def _run_cl_turn(db, session_id, content="Make it punchier"):
    stream = history_chat.stream_cover_letter_chat_turn(
        session_id=session_id,
        req=ChatMessageRequest(content=content),
        db=db,
        llm=("openai/test-model", "test-key"),
    )
    return asyncio.run(_drain(stream))


# --- CV chat turn ---


def test_create_cv_chat_session_anchors_at_the_given_entry():
    db = make_session()
    entry = _cv(db)
    session = history_chat.create_cv_chat(entry_id=entry.id, db=db)
    assert session.turn_count == 0
    assert session.status == "open"


def test_create_cv_chat_404s_for_a_missing_entry():
    db = make_session()
    with pytest.raises(HistoryEntryNotFoundError):
        history_chat.create_cv_chat(entry_id=999, db=db)


def test_stream_turn_with_no_patch_persists_both_messages_and_increments_turn_count(monkeypatch):
    db = make_session()
    entry = _cv(db)
    session = history_chat.create_cv_chat(entry_id=entry.id, db=db)

    async def fake_stream_llm(*args, **kwargs):
        yield "Sure, happy to help - what would you like to change?"

    monkeypatch.setattr(history_chat, "stream_llm", fake_stream_llm)

    events = _run_cv_turn(db, session.id, content="Hi, can you help me improve my CV?")

    assert [e.event for e in events] == ["token", "done"]
    messages = db.query(CvChatMessage).filter_by(session_id=session.id).order_by(CvChatMessage.id).all()
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[0].content == "Hi, can you help me improve my CV?"
    assert messages[1].role == "assistant"
    assert messages[1].proposed_patch_json is None
    assert messages[1].patch_status is None

    refreshed = history_chat.get_cv_chat_session(db, session.id)
    assert refreshed.turn_count == 1


def test_stream_turn_with_a_patch_marks_it_pending_and_emits_a_patch_event(monkeypatch):
    db = make_session()
    entry = _cv(db)
    session = history_chat.create_cv_chat(entry_id=entry.id, db=db)

    async def fake_stream_llm(*args, **kwargs):
        yield "I'll tighten the summary.\n%%%PATCH_JSON%%%\n"
        yield '{"target": {"section": "summary"}, "new_value": "Tighter summary."}'

    monkeypatch.setattr(history_chat, "stream_llm", fake_stream_llm)

    events = _run_cv_turn(db, session.id)

    patch_events = [e for e in events if e.event == "patch"]
    assert len(patch_events) == 1
    payload = json.loads(patch_events[0].data)
    assert payload["new_value"] == "Tighter summary."
    assert payload["target"]["section"] == "summary"

    message = db.query(CvChatMessage).filter_by(session_id=session.id, role="assistant").first()
    assert message.patch_status == "pending"
    assert json.loads(message.proposed_patch_json)["new_value"] == "Tighter summary."


def test_stream_turn_falls_back_to_no_patch_on_malformed_target(monkeypatch):
    db = make_session()
    entry = _cv(db)
    session = history_chat.create_cv_chat(entry_id=entry.id, db=db)

    async def fake_stream_llm(*args, **kwargs):
        yield "Odd reply.\n%%%PATCH_JSON%%%\n"
        yield '{"target": {"section": "not_a_real_section"}, "new_value": "x"}'

    monkeypatch.setattr(history_chat, "stream_llm", fake_stream_llm)

    events = _run_cv_turn(db, session.id)

    assert not any(e.event == "patch" for e in events)
    message = db.query(CvChatMessage).filter_by(session_id=session.id, role="assistant").first()
    assert message.patch_status is None
    assert message.proposed_patch_json is None


def test_stream_turn_rejects_when_the_turn_cap_is_reached(monkeypatch):
    db = make_session()
    entry = _cv(db)
    response = history_chat.create_cv_chat(entry_id=entry.id, db=db)
    session = history_chat.get_cv_chat_session(db, response.id)
    session.turn_count = history_chat.MAX_TURNS_PER_SESSION
    db.commit()

    called = False

    async def fake_stream_llm(*args, **kwargs):
        nonlocal called
        called = True
        yield "should not run"

    monkeypatch.setattr(history_chat, "stream_llm", fake_stream_llm)

    # Guardrail failures are yielded as an `error` event rather than raised
    # directly - by the time this generator runs, FastAPI's SSE machinery
    # has already started sending 200 response headers concurrently, so a
    # raised exception here would arrive too late to change the HTTP status.
    events = _run_cv_turn(db, session.id)
    assert events[-1].event == "error"
    assert called is False


def test_stream_turn_rejects_when_a_patch_is_already_pending(monkeypatch):
    db = make_session()
    entry = _cv(db)
    session = history_chat.create_cv_chat(entry_id=entry.id, db=db)
    db.add(
        CvChatMessage(
            session_id=session.id,
            role="assistant",
            content="proposed something",
            proposed_patch_json='{"target": {"section": "summary"}, "new_value": "x"}',
            patch_status="pending",
        )
    )
    db.commit()

    called = False

    async def fake_stream_llm(*args, **kwargs):
        nonlocal called
        called = True
        yield "should not run"

    monkeypatch.setattr(history_chat, "stream_llm", fake_stream_llm)

    events = _run_cv_turn(db, session.id)
    assert events[-1].event == "error"
    assert called is False


def test_apply_creates_exactly_one_new_version_and_updates_session_current_cv_id(monkeypatch):
    db = make_session()
    entry = _cv(db)
    session = history_chat.create_cv_chat(entry_id=entry.id, db=db)

    async def fake_stream_llm(*args, **kwargs):
        yield "I'll tighten the summary.\n%%%PATCH_JSON%%%\n"
        yield '{"target": {"section": "summary"}, "new_value": "Tighter summary."}'

    monkeypatch.setattr(history_chat, "stream_llm", fake_stream_llm)
    _run_cv_turn(db, session.id)

    message = db.query(CvChatMessage).filter_by(session_id=session.id, role="assistant").first()
    result = history_chat.apply_cv_chat_patch(session_id=session.id, message_id=message.id, db=db)

    assert db.query(GeneratedCV).count() == 2
    new_snapshot = json.loads(result["profile_snapshot"])
    assert new_snapshot["summary"] == "Tighter summary."
    assert result["edit_source"] == "ai_chat"

    refreshed_session = history_chat.get_cv_chat_session(db, session.id)
    assert refreshed_session.current_cv_id == result["id"]
    refreshed_message = db.query(CvChatMessage).filter_by(id=message.id).first()
    assert refreshed_message.patch_status == "applied"
    assert refreshed_message.resulting_cv_id == result["id"]


def test_discard_creates_zero_new_versions(monkeypatch):
    db = make_session()
    entry = _cv(db)
    session = history_chat.create_cv_chat(entry_id=entry.id, db=db)

    async def fake_stream_llm(*args, **kwargs):
        yield "I'll tighten the summary.\n%%%PATCH_JSON%%%\n"
        yield '{"target": {"section": "summary"}, "new_value": "Tighter summary."}'

    monkeypatch.setattr(history_chat, "stream_llm", fake_stream_llm)
    _run_cv_turn(db, session.id)

    message = db.query(CvChatMessage).filter_by(session_id=session.id, role="assistant").first()
    result = history_chat.discard_cv_chat_patch(session_id=session.id, message_id=message.id, db=db)

    assert result.status == "discarded"
    assert db.query(GeneratedCV).count() == 1
    refreshed_message = db.query(CvChatMessage).filter_by(id=message.id).first()
    assert refreshed_message.patch_status == "discarded"
    refreshed_session = history_chat.get_cv_chat_session(db, session.id)
    assert refreshed_session.current_cv_id == entry.id


def test_apply_rejects_a_message_that_is_no_longer_pending(monkeypatch):
    db = make_session()
    entry = _cv(db)
    session = history_chat.create_cv_chat(entry_id=entry.id, db=db)

    async def fake_stream_llm(*args, **kwargs):
        yield "I'll tighten the summary.\n%%%PATCH_JSON%%%\n"
        yield '{"target": {"section": "summary"}, "new_value": "Tighter summary."}'

    monkeypatch.setattr(history_chat, "stream_llm", fake_stream_llm)
    _run_cv_turn(db, session.id)
    message = db.query(CvChatMessage).filter_by(session_id=session.id, role="assistant").first()
    history_chat.discard_cv_chat_patch(session_id=session.id, message_id=message.id, db=db)

    with pytest.raises(InvalidRequestError):
        history_chat.apply_cv_chat_patch(session_id=session.id, message_id=message.id, db=db)


def test_apply_404s_when_the_message_belongs_to_a_different_session(monkeypatch):
    db = make_session()
    entry = _cv(db)
    session_a = history_chat.create_cv_chat(entry_id=entry.id, db=db)
    session_b = history_chat.create_cv_chat(entry_id=entry.id, db=db)

    async def fake_stream_llm(*args, **kwargs):
        yield "ok.\n%%%PATCH_JSON%%%\n"
        yield '{"target": {"section": "summary"}, "new_value": "x"}'

    monkeypatch.setattr(history_chat, "stream_llm", fake_stream_llm)
    _run_cv_turn(db, session_a.id)
    message = db.query(CvChatMessage).filter_by(session_id=session_a.id, role="assistant").first()

    with pytest.raises(HistoryEntryNotFoundError):
        history_chat.apply_cv_chat_patch(session_id=session_b.id, message_id=message.id, db=db)


# --- Cover letter chat turn ---


def test_stream_cl_turn_with_a_patch_and_apply_creates_one_new_version(monkeypatch):
    db = make_session()
    entry = _cl(db)
    session = history_chat.create_cover_letter_chat(entry_id=entry.id, db=db)

    async def fake_stream_llm(*args, **kwargs):
        yield "Here's a warmer opening.\n%%%PATCH_JSON%%%\n"
        yield '{"new_value": "Dear team, I am thrilled to apply."}'

    monkeypatch.setattr(history_chat, "stream_llm", fake_stream_llm)
    events = _run_cl_turn(db, session.id)
    assert any(e.event == "patch" for e in events)

    message = db.query(CoverLetterChatMessage).filter_by(session_id=session.id, role="assistant").first()
    result = history_chat.apply_cover_letter_chat_patch(
        session_id=session.id, message_id=message.id, db=db
    )

    assert db.query(GeneratedCoverLetter).count() == 2
    assert result["cover_letter_text"] == "Dear team, I am thrilled to apply."
    assert result["edit_source"] == "ai_chat"
    refreshed_session = history_chat.get_cover_letter_chat_session(db, session.id)
    assert refreshed_session.current_cl_id == result["id"]


def test_discard_cl_creates_zero_new_versions(monkeypatch):
    db = make_session()
    entry = _cl(db)
    session = history_chat.create_cover_letter_chat(entry_id=entry.id, db=db)

    async def fake_stream_llm(*args, **kwargs):
        yield "ok.\n%%%PATCH_JSON%%%\n"
        yield '{"new_value": "New text."}'

    monkeypatch.setattr(history_chat, "stream_llm", fake_stream_llm)
    _run_cl_turn(db, session.id)
    message = db.query(CoverLetterChatMessage).filter_by(session_id=session.id, role="assistant").first()

    result = history_chat.discard_cover_letter_chat_patch(
        session_id=session.id, message_id=message.id, db=db
    )
    assert result.status == "discarded"
    assert db.query(GeneratedCoverLetter).count() == 1
