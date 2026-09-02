import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.role_match.models  # noqa: F401 - registers role_match tables on Base
from app.exceptions import HistoryEntryNotFoundError
from app.models import Base, GeneratedCoverLetter, GeneratedCV
from app.routes import history_edit
from app.schemas import (
    CoverLetterSelectionEditStreamRequest,
    CvEditTarget,
    CvSelectionEditStreamRequest,
)


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _cv(db, **overrides) -> GeneratedCV:
    base = dict(
        enhanced=0,
        profile_snapshot='{"name":"Jane","email":"jane@example.com","summary":"Old summary.","work_experience":[{"company":"Acme","role":"Engineer","start_date":"2020","end_date":null,"bullets":["Built X"]}]}',
    )
    base.update(overrides)
    entry = GeneratedCV(**base)
    db.add(entry)
    db.commit()
    return entry


def _cl(db, **overrides) -> GeneratedCoverLetter:
    base = dict(job_description="desc", cover_letter_text="I am excited about this role.", tone="professional")
    base.update(overrides)
    entry = GeneratedCoverLetter(**base)
    db.add(entry)
    db.commit()
    return entry


def test_stream_cv_selection_edit_yields_tokens_then_done(monkeypatch):
    db = make_session()
    entry = _cv(db)

    async def fake_stream_llm(*args, **kwargs):
        yield "- Rewritten "
        yield "bullet"

    monkeypatch.setattr(history_edit, "stream_llm", fake_stream_llm)

    req = CvSelectionEditStreamRequest(
        target=CvEditTarget(section="work_experience", index=0, subfield="bullets"),
        instruction="Make it punchier",
    )

    async def run():
        stream = history_edit.stream_cv_selection_edit(
            entry_id=entry.id, req=req, db=db, llm=("openai/test-model", "test-key")
        )
        events = [await anext(stream), await anext(stream), await anext(stream)]
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
        return events

    events = asyncio.run(run())
    assert [e.data for e in events] == ["- Rewritten ", "bullet", "[DONE]"]
    assert events[0].event == "token"
    assert events[-1].event == "done"


def test_stream_cv_selection_edit_404s_for_a_missing_entry(monkeypatch):
    db = make_session()

    req = CvSelectionEditStreamRequest(
        target=CvEditTarget(section="summary"), instruction="Shorten it"
    )

    async def run():
        stream = history_edit.stream_cv_selection_edit(
            entry_id=999, req=req, db=db, llm=("openai/test-model", "test-key")
        )
        await anext(stream)

    with pytest.raises(HistoryEntryNotFoundError):
        asyncio.run(run())


def test_stream_cv_selection_edit_surfaces_llm_errors_via_error_event(monkeypatch):
    db = make_session()
    entry = _cv(db)

    async def failing_stream_llm(*args, **kwargs):
        raise RuntimeError("provider exploded")
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(history_edit, "stream_llm", failing_stream_llm)

    req = CvSelectionEditStreamRequest(
        target=CvEditTarget(section="summary"), instruction="Shorten it"
    )

    async def run():
        stream = history_edit.stream_cv_selection_edit(
            entry_id=entry.id, req=req, db=db, llm=("openai/test-model", "test-key")
        )
        event = await anext(stream)
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
        return event

    event = asyncio.run(run())
    assert event.event == "error"


def test_stream_cover_letter_selection_edit_yields_tokens_then_done(monkeypatch):
    db = make_session()
    entry = _cl(db)

    async def fake_stream_llm(*args, **kwargs):
        yield "I am thrilled"

    monkeypatch.setattr(history_edit, "stream_llm", fake_stream_llm)

    req = CoverLetterSelectionEditStreamRequest(
        excerpt="I am excited", instruction="Make it more enthusiastic"
    )

    async def run():
        stream = history_edit.stream_cover_letter_selection_edit(
            entry_id=entry.id, req=req, db=db, llm=("openai/test-model", "test-key")
        )
        events = [await anext(stream), await anext(stream)]
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
        return events

    events = asyncio.run(run())
    assert [e.data for e in events] == ["I am thrilled", "[DONE]"]


def test_stream_cover_letter_selection_edit_404s_for_a_missing_entry():
    db = make_session()
    req = CoverLetterSelectionEditStreamRequest(excerpt="text", instruction="Rewrite")

    async def run():
        stream = history_edit.stream_cover_letter_selection_edit(
            entry_id=999, req=req, db=db, llm=("openai/test-model", "test-key")
        )
        await anext(stream)

    with pytest.raises(HistoryEntryNotFoundError):
        asyncio.run(run())
