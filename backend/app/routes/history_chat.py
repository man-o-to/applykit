import json
from collections.abc import AsyncIterable

from fastapi import APIRouter, Depends
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_llm_config
from app.exceptions import HistoryEntryNotFoundError, InvalidRequestError, stream_error_event
from app.history.snapshots import save_cover_letter_version, save_cv_version
from app.history.targets import get_cv_target_value, set_cv_target_value
from app.history_chat.repository import (
    CHAT_HISTORY_WINDOW,
    MAX_TURNS_PER_SESSION,
    create_cover_letter_chat_session,
    create_cv_chat_session,
    get_cover_letter_chat_session,
    get_cv_chat_session,
    get_pending_cover_letter_chat_message,
    get_pending_cv_chat_message,
    list_cover_letter_chat_messages,
    list_cv_chat_messages,
)
from app.models import CoverLetterChatMessage, CvChatMessage, GeneratedCoverLetter, GeneratedCV
from app.role_match.product_schemas import RoleMatchGeneratedCoverLetterEntry
from app.routes.history import _enrich_cl, _enrich_cv
from app.schemas import (
    ChatMessageItem,
    ChatMessageRequest,
    ChatMessagesResponse,
    ChatPatchActionResponse,
    ChatSessionResponse,
    CvEditTarget,
    GeneratedCVEntry,
    ProfileData,
)
from app.services.chat_patch import safe_emit_length, split_reply_and_patch
from app.services.llm import (
    OPERATION_COVER_LETTER_CHAT_EDIT,
    OPERATION_CV_CHAT_EDIT,
    stream_llm,
)
from app.services.prompts import (
    COVER_LETTER_CHAT_SYSTEM_PROMPT,
    CV_CHAT_SYSTEM_PROMPT,
    format_untrusted_input,
)
from app.utils import batch_load_profiles

router = APIRouter()


def _session_to_response(session) -> ChatSessionResponse:
    return ChatSessionResponse(
        id=session.id,
        status=session.status,
        turn_count=session.turn_count,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _message_to_item(message) -> ChatMessageItem:
    patch = json.loads(message.proposed_patch_json) if message.proposed_patch_json else None
    resulting_id = getattr(message, "resulting_cv_id", None) or getattr(
        message, "resulting_cl_id", None
    )
    return ChatMessageItem(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        proposed_patch=patch,
        patch_status=message.patch_status,
        resulting_version_id=resulting_id,
    )


def _history_messages(messages: list) -> list[dict]:
    windowed = messages[-CHAT_HISTORY_WINDOW:]
    return [{"role": m.role, "content": m.content} for m in windowed]


# --- CV chat ---


@router.post("/history/cv/{entry_id}/chat/sessions", response_model=ChatSessionResponse)
def create_cv_chat(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(GeneratedCV).filter_by(id=entry_id).first()
    if not entry:
        raise HistoryEntryNotFoundError("CV entry", entry_id)
    if entry.superseded_by_id is not None:
        raise InvalidRequestError(
            "This version has already been superseded by a newer edit. Reload to see the latest version."
        )
    session = create_cv_chat_session(db, cv_id=entry.id)
    return _session_to_response(session)


@router.get("/history/cv/chat/sessions/{session_id}", response_model=ChatSessionResponse)
def get_cv_chat(session_id: int, db: Session = Depends(get_db)):
    session = get_cv_chat_session(db, session_id)
    if not session:
        raise HistoryEntryNotFoundError("Chat session", session_id)
    return _session_to_response(session)


@router.get(
    "/history/cv/chat/sessions/{session_id}/messages", response_model=ChatMessagesResponse
)
def list_cv_chat(session_id: int, db: Session = Depends(get_db)):
    session = get_cv_chat_session(db, session_id)
    if not session:
        raise HistoryEntryNotFoundError("Chat session", session_id)
    messages = list_cv_chat_messages(db, session_id)
    return ChatMessagesResponse(items=[_message_to_item(m) for m in messages])


@router.post(
    "/history/cv/chat/sessions/{session_id}/messages/stream",
    response_class=EventSourceResponse,
)
async def stream_cv_chat_turn(
    session_id: int,
    req: ChatMessageRequest,
    db: Session = Depends(get_db),
    llm: tuple[str, str] = Depends(require_llm_config),
) -> AsyncIterable[ServerSentEvent]:
    # Everything below - including plain validation - must stay inside this
    # try/except. FastAPI's SSE handling starts sending the 200 response
    # headers concurrently with entering this generator, not after it first
    # yields, so an exception raised directly (rather than yielded as an
    # `error` event) can arrive too late to change the HTTP status and
    # surfaces as an opaque broken response instead of the intended 4xx.
    try:
        session = get_cv_chat_session(db, session_id)
        if not session:
            raise HistoryEntryNotFoundError("Chat session", session_id)
        if session.turn_count >= MAX_TURNS_PER_SESSION:
            raise InvalidRequestError(
                "This chat session has reached its turn limit. Start a new session to keep editing."
            )
        if get_pending_cv_chat_message(db, session_id) is not None:
            raise InvalidRequestError(
                "This session has a proposed edit waiting to be applied or discarded."
            )
        entry = db.query(GeneratedCV).filter_by(id=session.current_cv_id).first()
        if not entry:
            raise HistoryEntryNotFoundError("CV entry", session.current_cv_id or 0)

        provider, api_key = llm
        history = _history_messages(list_cv_chat_messages(db, session_id))
        profile_json = json.loads(entry.profile_snapshot)
        user_prompt = "\n".join(
            [
                format_untrusted_input("current_cv", profile_json),
                f"CANDIDATE MESSAGE: {req.content.strip()}",
            ]
        )

        raw_text = ""
        emitted_length = 0
        async for chunk in stream_llm(
            user_prompt,
            system=CV_CHAT_SYSTEM_PROMPT,
            history=history,
            provider=provider,
            api_key=api_key,
            operation=OPERATION_CV_CHAT_EDIT,
            profile_id=entry.profile_id,
        ):
            raw_text += chunk
            safe_len = safe_emit_length(raw_text)
            if safe_len > emitted_length:
                yield ServerSentEvent(data=json.dumps(raw_text[emitted_length:safe_len]), event="token")
                emitted_length = safe_len

        reply, raw_patch = split_reply_and_patch(raw_text)
        if len(reply) > emitted_length:
            yield ServerSentEvent(data=json.dumps(reply[emitted_length:]), event="token")

        patch = _validate_cv_patch(raw_patch)

        user_message = CvChatMessage(session_id=session.id, role="user", content=req.content)
        assistant_message = CvChatMessage(
            session_id=session.id,
            role="assistant",
            content=reply,
            proposed_patch_json=json.dumps(patch) if patch else None,
            patch_status="pending" if patch else None,
        )
        db.add(user_message)
        db.add(assistant_message)
        session.turn_count += 1
        db.commit()
        db.refresh(assistant_message)
    except Exception as exc:
        yield stream_error_event(exc)
        return

    if patch:
        yield ServerSentEvent(
            data=json.dumps({"message_id": assistant_message.id, **patch}), event="patch"
        )
    yield ServerSentEvent(
        data=json.dumps({"message_id": assistant_message.id, "turn_count": session.turn_count}),
        event="done",
    )


@router.post(
    "/history/cv/chat/sessions/{session_id}/messages/{message_id}/apply",
    response_model=GeneratedCVEntry,
)
def apply_cv_chat_patch(session_id: int, message_id: int, db: Session = Depends(get_db)):
    session, message = _load_pending_cv_message(db, session_id, message_id)
    entry = db.query(GeneratedCV).filter_by(id=session.current_cv_id).first()
    if not entry:
        raise HistoryEntryNotFoundError("CV entry", session.current_cv_id or 0)
    if entry.superseded_by_id is not None:
        raise InvalidRequestError(
            "This version has already been superseded by a newer edit. Reload to see the latest version."
        )

    patch = json.loads(message.proposed_patch_json)
    target = CvEditTarget(**patch["target"])
    profile = ProfileData.model_validate_json(entry.profile_snapshot)
    original_value = get_cv_target_value(profile, target)
    set_cv_target_value(profile, target, patch["new_value"])

    version = save_cv_version(
        db,
        parent=entry,
        profile_snapshot=profile.model_dump_json(),
        edit_source="ai_chat",
        edit_instruction=message.content,
        edit_target_excerpt=_stringify(original_value),
    )
    version.chat_session_id = session.id
    session.current_cv_id = version.id
    message.patch_status = "applied"
    message.resulting_cv_id = version.id
    db.commit()
    db.refresh(version)
    return _enrich_cv(version, batch_load_profiles([version], db))


@router.post(
    "/history/cv/chat/sessions/{session_id}/messages/{message_id}/discard",
    response_model=ChatPatchActionResponse,
)
def discard_cv_chat_patch(session_id: int, message_id: int, db: Session = Depends(get_db)):
    _, message = _load_pending_cv_message(db, session_id, message_id)
    message.patch_status = "discarded"
    db.commit()
    return ChatPatchActionResponse(status="discarded", message_id=message.id)


def _load_pending_cv_message(db: Session, session_id: int, message_id: int):
    session = get_cv_chat_session(db, session_id)
    if not session:
        raise HistoryEntryNotFoundError("Chat session", session_id)
    message = db.query(CvChatMessage).filter_by(id=message_id).first()
    if not message or message.session_id != session.id:
        raise HistoryEntryNotFoundError("Chat message", message_id)
    if message.patch_status != "pending":
        raise InvalidRequestError("This proposed edit is no longer pending.")
    return session, message


def _validate_cv_patch(raw_patch: dict | None) -> dict | None:
    if raw_patch is None:
        return None
    try:
        target = CvEditTarget(**raw_patch["target"])
    except (KeyError, TypeError, ValueError):
        return None
    if "new_value" not in raw_patch:
        return None
    return {"target": target.model_dump(), "new_value": raw_patch["new_value"]}


def _stringify(value) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value) if value is not None else ""


# --- Cover letter chat ---


@router.post(
    "/history/cover-letter/{entry_id}/chat/sessions", response_model=ChatSessionResponse
)
def create_cover_letter_chat(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(GeneratedCoverLetter).filter_by(id=entry_id).first()
    if not entry:
        raise HistoryEntryNotFoundError("Cover letter", entry_id)
    if entry.superseded_by_id is not None:
        raise InvalidRequestError(
            "This version has already been superseded by a newer edit. Reload to see the latest version."
        )
    session = create_cover_letter_chat_session(db, cl_id=entry.id)
    return _session_to_response(session)


@router.get(
    "/history/cover-letter/chat/sessions/{session_id}", response_model=ChatSessionResponse
)
def get_cover_letter_chat(session_id: int, db: Session = Depends(get_db)):
    session = get_cover_letter_chat_session(db, session_id)
    if not session:
        raise HistoryEntryNotFoundError("Chat session", session_id)
    return _session_to_response(session)


@router.get(
    "/history/cover-letter/chat/sessions/{session_id}/messages",
    response_model=ChatMessagesResponse,
)
def list_cover_letter_chat(session_id: int, db: Session = Depends(get_db)):
    session = get_cover_letter_chat_session(db, session_id)
    if not session:
        raise HistoryEntryNotFoundError("Chat session", session_id)
    messages = list_cover_letter_chat_messages(db, session_id)
    return ChatMessagesResponse(items=[_message_to_item(m) for m in messages])


@router.post(
    "/history/cover-letter/chat/sessions/{session_id}/messages/stream",
    response_class=EventSourceResponse,
)
async def stream_cover_letter_chat_turn(
    session_id: int,
    req: ChatMessageRequest,
    db: Session = Depends(get_db),
    llm: tuple[str, str] = Depends(require_llm_config),
) -> AsyncIterable[ServerSentEvent]:
    # Everything below - including plain validation - must stay inside this
    # try/except. FastAPI's SSE handling starts sending the 200 response
    # headers concurrently with entering this generator, not after it first
    # yields, so an exception raised directly (rather than yielded as an
    # `error` event) can arrive too late to change the HTTP status and
    # surfaces as an opaque broken response instead of the intended 4xx.
    try:
        session = get_cover_letter_chat_session(db, session_id)
        if not session:
            raise HistoryEntryNotFoundError("Chat session", session_id)
        if session.turn_count >= MAX_TURNS_PER_SESSION:
            raise InvalidRequestError(
                "This chat session has reached its turn limit. Start a new session to keep editing."
            )
        if get_pending_cover_letter_chat_message(db, session_id) is not None:
            raise InvalidRequestError(
                "This session has a proposed edit waiting to be applied or discarded."
            )
        entry = db.query(GeneratedCoverLetter).filter_by(id=session.current_cl_id).first()
        if not entry:
            raise HistoryEntryNotFoundError("Cover letter", session.current_cl_id or 0)

        provider, api_key = llm
        history = _history_messages(list_cover_letter_chat_messages(db, session_id))
        user_prompt = "\n".join(
            [
                format_untrusted_input("current_letter", entry.cover_letter_text),
                f"CANDIDATE MESSAGE: {req.content.strip()}",
            ]
        )

        raw_text = ""
        emitted_length = 0
        async for chunk in stream_llm(
            user_prompt,
            system=COVER_LETTER_CHAT_SYSTEM_PROMPT,
            history=history,
            provider=provider,
            api_key=api_key,
            operation=OPERATION_COVER_LETTER_CHAT_EDIT,
            profile_id=entry.profile_id,
        ):
            raw_text += chunk
            safe_len = safe_emit_length(raw_text)
            if safe_len > emitted_length:
                yield ServerSentEvent(data=json.dumps(raw_text[emitted_length:safe_len]), event="token")
                emitted_length = safe_len

        reply, raw_patch = split_reply_and_patch(raw_text)
        if len(reply) > emitted_length:
            yield ServerSentEvent(data=json.dumps(reply[emitted_length:]), event="token")

        patch = raw_patch if raw_patch and "new_value" in raw_patch else None

        user_message = CoverLetterChatMessage(session_id=session.id, role="user", content=req.content)
        assistant_message = CoverLetterChatMessage(
            session_id=session.id,
            role="assistant",
            content=reply,
            proposed_patch_json=json.dumps(patch) if patch else None,
            patch_status="pending" if patch else None,
        )
        db.add(user_message)
        db.add(assistant_message)
        session.turn_count += 1
        db.commit()
        db.refresh(assistant_message)
    except Exception as exc:
        yield stream_error_event(exc)
        return

    if patch:
        yield ServerSentEvent(
            data=json.dumps({"message_id": assistant_message.id, **patch}), event="patch"
        )
    yield ServerSentEvent(
        data=json.dumps({"message_id": assistant_message.id, "turn_count": session.turn_count}),
        event="done",
    )


@router.post(
    "/history/cover-letter/chat/sessions/{session_id}/messages/{message_id}/apply",
    response_model=RoleMatchGeneratedCoverLetterEntry,
)
def apply_cover_letter_chat_patch(
    session_id: int, message_id: int, db: Session = Depends(get_db)
):
    session, message = _load_pending_cl_message(db, session_id, message_id)
    entry = db.query(GeneratedCoverLetter).filter_by(id=session.current_cl_id).first()
    if not entry:
        raise HistoryEntryNotFoundError("Cover letter", session.current_cl_id or 0)
    if entry.superseded_by_id is not None:
        raise InvalidRequestError(
            "This version has already been superseded by a newer edit. Reload to see the latest version."
        )

    patch = json.loads(message.proposed_patch_json)
    version = save_cover_letter_version(
        db,
        parent=entry,
        cover_letter_text=patch["new_value"],
        edit_source="ai_chat",
        edit_instruction=message.content,
    )
    version.chat_session_id = session.id
    session.current_cl_id = version.id
    message.patch_status = "applied"
    message.resulting_cl_id = version.id
    db.commit()
    db.refresh(version)
    return _enrich_cl(version, batch_load_profiles([version], db), db)


@router.post(
    "/history/cover-letter/chat/sessions/{session_id}/messages/{message_id}/discard",
    response_model=ChatPatchActionResponse,
)
def discard_cover_letter_chat_patch(
    session_id: int, message_id: int, db: Session = Depends(get_db)
):
    _, message = _load_pending_cl_message(db, session_id, message_id)
    message.patch_status = "discarded"
    db.commit()
    return ChatPatchActionResponse(status="discarded", message_id=message.id)


def _load_pending_cl_message(db: Session, session_id: int, message_id: int):
    session = get_cover_letter_chat_session(db, session_id)
    if not session:
        raise HistoryEntryNotFoundError("Chat session", session_id)
    message = db.query(CoverLetterChatMessage).filter_by(id=message_id).first()
    if not message or message.session_id != session.id:
        raise HistoryEntryNotFoundError("Chat message", message_id)
    if message.patch_status != "pending":
        raise InvalidRequestError("This proposed edit is no longer pending.")
    return session, message
