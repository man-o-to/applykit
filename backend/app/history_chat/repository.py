from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import (
    CoverLetterChatMessage,
    CoverLetterChatSession,
    CvChatMessage,
    CvChatSession,
)

# Hard cap on turns per session. A capped-out session can't send another
# message - the user opens a fresh session anchored at the current head.
MAX_TURNS_PER_SESSION = 20

# How many of the most recent stored messages are sent to the model as
# conversation history each turn. Deliberately tighter than Phase 4's
# global MAX_HISTORY_MESSAGES cap - this is the window that actually kicks
# in during a normal session; Phase 4's cap is just the hard backstop.
CHAT_HISTORY_WINDOW = 8


def create_cv_chat_session(db: Session, *, cv_id: int) -> CvChatSession:
    session = CvChatSession(cv_root_id=cv_id, current_cv_id=cv_id, status="open", turn_count=0)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_cv_chat_session(db: Session, session_id: int) -> CvChatSession | None:
    return db.query(CvChatSession).filter_by(id=session_id).first()


def list_cv_chat_messages(db: Session, session_id: int) -> list[CvChatMessage]:
    return (
        db.query(CvChatMessage)
        .filter_by(session_id=session_id)
        .order_by(CvChatMessage.created_at.asc(), CvChatMessage.id.asc())
        .all()
    )


def get_pending_cv_chat_message(db: Session, session_id: int) -> CvChatMessage | None:
    return db.query(CvChatMessage).filter_by(session_id=session_id, patch_status="pending").first()


def create_cover_letter_chat_session(db: Session, *, cl_id: int) -> CoverLetterChatSession:
    session = CoverLetterChatSession(
        cl_root_id=cl_id, current_cl_id=cl_id, status="open", turn_count=0
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_cover_letter_chat_session(db: Session, session_id: int) -> CoverLetterChatSession | None:
    return db.query(CoverLetterChatSession).filter_by(id=session_id).first()


def list_cover_letter_chat_messages(db: Session, session_id: int) -> list[CoverLetterChatMessage]:
    return (
        db.query(CoverLetterChatMessage)
        .filter_by(session_id=session_id)
        .order_by(CoverLetterChatMessage.created_at.asc(), CoverLetterChatMessage.id.asc())
        .all()
    )


def get_pending_cover_letter_chat_message(
    db: Session, session_id: int
) -> CoverLetterChatMessage | None:
    return (
        db.query(CoverLetterChatMessage)
        .filter_by(session_id=session_id, patch_status="pending")
        .first()
    )
