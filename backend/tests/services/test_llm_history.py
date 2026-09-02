from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base
from app.services import llm as llm_service
from app.services.llm import MAX_HISTORY_MESSAGES, _prepare_messages, call_llm, stream_llm


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


# --- _prepare_messages: pure message-shape assertions ---


def test_history_none_produces_the_same_messages_as_before():
    """Regression guard: every existing single-turn caller must see byte-
    identical behavior when it doesn't pass history."""
    with_default = _prepare_messages("hello", system="be nice")
    explicit_none = _prepare_messages("hello", system="be nice", history=None)
    assert with_default == explicit_none == [
        {"role": "system", "content": "be nice"},
        {"role": "user", "content": "hello"},
    ]


def test_history_is_inserted_between_system_and_the_current_prompt():
    history = [
        {"role": "user", "content": "turn 1"},
        {"role": "assistant", "content": "reply 1"},
    ]

    messages = _prepare_messages("turn 2", system="be nice", history=history)

    assert messages == [
        {"role": "system", "content": "be nice"},
        {"role": "user", "content": "turn 1"},
        {"role": "assistant", "content": "reply 1"},
        {"role": "user", "content": "turn 2"},
    ]


def test_history_works_without_a_system_prompt():
    history = [{"role": "user", "content": "turn 1"}, {"role": "assistant", "content": "reply 1"}]

    messages = _prepare_messages("turn 2", history=history)

    assert messages == [
        {"role": "user", "content": "turn 1"},
        {"role": "assistant", "content": "reply 1"},
        {"role": "user", "content": "turn 2"},
    ]


def test_oversized_history_is_truncated_to_the_most_recent_entries():
    history = [{"role": "user", "content": f"turn {i}"} for i in range(MAX_HISTORY_MESSAGES + 10)]

    messages = _prepare_messages("current", system="sys", history=history)

    # system + the most recent MAX_HISTORY_MESSAGES entries + the current prompt.
    assert len(messages) == 1 + MAX_HISTORY_MESSAGES + 1
    assert messages[1] == {"role": "user", "content": "turn 10"}  # oldest entries dropped
    assert messages[-2] == {"role": "user", "content": f"turn {MAX_HISTORY_MESSAGES + 9}"}


# --- call_llm / stream_llm: the actual provider request carries history ---


def test_call_llm_forwards_history_to_the_provider_request(monkeypatch):
    db = _make_session()
    captured: dict[str, object] = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=None,
        )

    monkeypatch.setattr(llm_service.litellm, "completion", fake_completion)
    history = [{"role": "user", "content": "earlier turn"}, {"role": "assistant", "content": "earlier reply"}]

    try:
        result = call_llm(
            "current turn",
            system="sys",
            history=history,
            provider="ollama/llama3.2",
            credential_db=db,
        )
        assert result == "ok"
        assert captured["messages"] == [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "earlier turn"},
            {"role": "assistant", "content": "earlier reply"},
            {"role": "user", "content": "current turn"},
        ]
    finally:
        db.close()


@pytest.mark.anyio
async def test_stream_llm_forwards_history_to_the_provider_request(monkeypatch):
    db = _make_session()
    captured: dict[str, object] = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)

        async def chunks():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="ok"))],
                usage=None,
            )

        return chunks()

    monkeypatch.setattr(llm_service.litellm, "acompletion", fake_acompletion)
    history = [{"role": "user", "content": "earlier turn"}, {"role": "assistant", "content": "earlier reply"}]

    try:
        result = [
            chunk
            async for chunk in stream_llm(
                "current turn",
                system="sys",
                history=history,
                provider="ollama/llama3.2",
                credential_db=db,
            )
        ]
        assert result == ["ok"]
        assert captured["messages"] == [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "earlier turn"},
            {"role": "assistant", "content": "earlier reply"},
            {"role": "user", "content": "current turn"},
        ]
    finally:
        db.close()
