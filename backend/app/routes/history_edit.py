from collections.abc import AsyncIterable

from fastapi import APIRouter, Depends
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_llm_config
from app.exceptions import HistoryEntryNotFoundError, InvalidRequestError, stream_error_event
from app.history.snapshots import save_cover_letter_version, save_cv_version
from app.history.targets import get_cv_target_value, set_cv_target_value
from app.models import GeneratedCoverLetter, GeneratedCV
from app.role_match.product_schemas import RoleMatchGeneratedCoverLetterEntry
from app.routes.history import _enrich_cl, _enrich_cv
from app.schemas import (
    CoverLetterSelectionEditApplyRequest,
    CoverLetterSelectionEditStreamRequest,
    CvSelectionEditApplyRequest,
    CvSelectionEditStreamRequest,
    GeneratedCVEntry,
    ProfileData,
)
from app.services.llm import (
    OPERATION_COVER_LETTER_SELECTION_EDIT,
    OPERATION_CV_SELECTION_EDIT,
    stream_llm,
)
from app.services.prompts import (
    COVER_LETTER_SELECTION_REWRITE_PROMPT,
    CV_SELECTION_REWRITE_PROMPT,
    format_untrusted_input,
)
from app.utils import batch_load_profiles

router = APIRouter()


def _stringify_target_value(value) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value) if value is not None else ""


def _build_cv_selection_prompt(current_value, instruction: str) -> str:
    return "\n".join(
        [
            format_untrusted_input("current_value", current_value),
            f"INSTRUCTION: {instruction.strip()}",
        ]
    )


def _build_cover_letter_selection_prompt(excerpt: str, instruction: str) -> str:
    return "\n".join(
        [
            format_untrusted_input("excerpt", excerpt),
            f"INSTRUCTION: {instruction.strip()}",
        ]
    )


@router.post(
    "/history/cv/{entry_id}/edit/selection/stream",
    response_class=EventSourceResponse,
)
async def stream_cv_selection_edit(
    entry_id: int,
    req: CvSelectionEditStreamRequest,
    db: Session = Depends(get_db),
    llm: tuple[str, str] = Depends(require_llm_config),
) -> AsyncIterable[ServerSentEvent]:
    entry = db.query(GeneratedCV).filter_by(id=entry_id).first()
    if not entry:
        raise HistoryEntryNotFoundError("CV entry", entry_id)
    provider, api_key = llm

    profile = ProfileData.model_validate_json(entry.profile_snapshot)
    current_value = get_cv_target_value(profile, req.target)
    user_prompt = _build_cv_selection_prompt(current_value, req.instruction)

    try:
        async for chunk in stream_llm(
            user_prompt,
            system=CV_SELECTION_REWRITE_PROMPT,
            provider=provider,
            api_key=api_key,
            operation=OPERATION_CV_SELECTION_EDIT,
            profile_id=entry.profile_id,
        ):
            yield ServerSentEvent(data=str(chunk), event="token")
    except Exception as exc:
        yield stream_error_event(exc)
        return

    yield ServerSentEvent(data="[DONE]", event="done")


@router.post("/history/cv/{entry_id}/edit/selection/apply", response_model=GeneratedCVEntry)
def apply_cv_selection_edit(
    entry_id: int, req: CvSelectionEditApplyRequest, db: Session = Depends(get_db)
):
    entry = db.query(GeneratedCV).filter_by(id=entry_id).first()
    if not entry:
        raise HistoryEntryNotFoundError("CV entry", entry_id)
    if entry.superseded_by_id is not None:
        raise InvalidRequestError(
            "This version has already been superseded by a newer edit. Reload to see the latest version."
        )

    profile = ProfileData.model_validate_json(entry.profile_snapshot)
    original_value = get_cv_target_value(profile, req.target)
    set_cv_target_value(profile, req.target, req.new_value)

    version = save_cv_version(
        db,
        parent=entry,
        profile_snapshot=profile.model_dump_json(),
        edit_source="ai_selection",
        edit_instruction=req.instruction,
        edit_target_excerpt=_stringify_target_value(original_value),
    )
    return _enrich_cv(version, batch_load_profiles([version], db))


@router.post(
    "/history/cover-letter/{entry_id}/edit/selection/stream",
    response_class=EventSourceResponse,
)
async def stream_cover_letter_selection_edit(
    entry_id: int,
    req: CoverLetterSelectionEditStreamRequest,
    db: Session = Depends(get_db),
    llm: tuple[str, str] = Depends(require_llm_config),
) -> AsyncIterable[ServerSentEvent]:
    entry = db.query(GeneratedCoverLetter).filter_by(id=entry_id).first()
    if not entry:
        raise HistoryEntryNotFoundError("Cover letter", entry_id)
    provider, api_key = llm
    user_prompt = _build_cover_letter_selection_prompt(req.excerpt, req.instruction)

    try:
        async for chunk in stream_llm(
            user_prompt,
            system=COVER_LETTER_SELECTION_REWRITE_PROMPT,
            provider=provider,
            api_key=api_key,
            operation=OPERATION_COVER_LETTER_SELECTION_EDIT,
            profile_id=entry.profile_id,
        ):
            yield ServerSentEvent(data=str(chunk), event="token")
    except Exception as exc:
        yield stream_error_event(exc)
        return

    yield ServerSentEvent(data="[DONE]", event="done")


@router.post(
    "/history/cover-letter/{entry_id}/edit/selection/apply",
    response_model=RoleMatchGeneratedCoverLetterEntry,
)
def apply_cover_letter_selection_edit(
    entry_id: int,
    req: CoverLetterSelectionEditApplyRequest,
    db: Session = Depends(get_db),
):
    entry = db.query(GeneratedCoverLetter).filter_by(id=entry_id).first()
    if not entry:
        raise HistoryEntryNotFoundError("Cover letter", entry_id)
    if entry.superseded_by_id is not None:
        raise InvalidRequestError(
            "This version has already been superseded by a newer edit. Reload to see the latest version."
        )
    current_text = entry.cover_letter_text
    if (
        req.selection_start < 0
        or req.selection_end > len(current_text)
        or req.selection_start > req.selection_end
        or current_text[req.selection_start : req.selection_end] != req.excerpt
    ):
        raise InvalidRequestError(
            "The selected text has changed since it was chosen. Reload and try again."
        )

    new_text = (
        current_text[: req.selection_start]
        + req.new_value
        + current_text[req.selection_end :]
    )

    version = save_cover_letter_version(
        db,
        parent=entry,
        cover_letter_text=new_text,
        edit_source="ai_selection",
        edit_instruction=req.instruction,
        edit_target_excerpt=req.excerpt,
    )
    return _enrich_cl(version, batch_load_profiles([version], db), db)
