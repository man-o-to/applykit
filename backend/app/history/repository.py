from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import GeneratedCoverLetter, GeneratedCV
from app.services.version_chain import walk_version_chain


def list_cv_chain(db: Session, cv: GeneratedCV) -> list[GeneratedCV]:
    return walk_version_chain(db, GeneratedCV, cv)


def list_cl_chain(db: Session, cl: GeneratedCoverLetter) -> list[GeneratedCoverLetter]:
    return walk_version_chain(db, GeneratedCoverLetter, cl)


def delete_cv_chain(db: Session, cv_id: int) -> int:
    """Delete every version in the chain containing cv_id, in one
    transaction. Deleting only the target row would leave self-referential
    SET NULL FKs to silently orphan any mid-chain children."""
    entry = db.query(GeneratedCV).filter_by(id=cv_id).first()
    if entry is None:
        return 0
    chain = list_cv_chain(db, entry)
    ids = [item.id for item in chain]
    deleted = (
        db.query(GeneratedCV).filter(GeneratedCV.id.in_(ids)).delete(synchronize_session=False)
    )
    db.commit()
    return deleted


def delete_cl_chain(db: Session, cl_id: int) -> int:
    entry = db.query(GeneratedCoverLetter).filter_by(id=cl_id).first()
    if entry is None:
        return 0
    chain = list_cl_chain(db, entry)
    ids = [item.id for item in chain]
    deleted = (
        db.query(GeneratedCoverLetter)
        .filter(GeneratedCoverLetter.id.in_(ids))
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted
