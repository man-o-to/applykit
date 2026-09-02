from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.role_match.models  # noqa: F401 - registers role_match tables on Base
from app.history.snapshots import save_cover_letter_version, save_cv_version
from app.models import Base, GeneratedCoverLetter, GeneratedCV
from app.routes.history import (
    bulk_delete_cover_letters,
    bulk_delete_cvs,
    delete_cover_letter_history_entry,
    delete_cv_history_entry,
    list_cover_letter_history,
    list_cv_history,
)
from app.schemas import BulkDeleteRequest


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _cv(db, **overrides) -> GeneratedCV:
    base = dict(enhanced=0, profile_snapshot="{}", profile_id=None, application_id=None)
    base.update(overrides)
    entry = GeneratedCV(**base)
    db.add(entry)
    db.commit()
    return entry


def _cl(db, **overrides) -> GeneratedCoverLetter:
    base = dict(
        company_name="Acme",
        job_description="desc",
        cover_letter_text="Dear hiring manager,",
        tone="professional",
    )
    base.update(overrides)
    entry = GeneratedCoverLetter(**base)
    db.add(entry)
    db.commit()
    return entry


def test_list_cv_history_only_returns_the_chain_head():
    db = make_session()
    v1 = _cv(db)
    v2 = save_cv_version(db, parent=v1, profile_snapshot="{}", edit_source="manual")

    result = list_cv_history(db=db, profile_id=None, sort="date_desc", limit=20, offset=0)

    ids = [item.id for item in result.items]
    assert v2.id in ids
    assert v1.id not in ids


def test_list_cover_letter_history_only_returns_the_chain_head():
    db = make_session()
    v1 = _cl(db)
    v2 = save_cover_letter_version(
        db, parent=v1, cover_letter_text="edited", edit_source="manual"
    )

    result = list_cover_letter_history(
        db=db,
        profile_id=None,
        search=None,
        match_min=None,
        match_max=None,
        status=None,
        sort="date_desc",
        limit=20,
        offset=0,
    )

    ids = [item.id for item in result.items]
    assert v2.id in ids
    assert v1.id not in ids


def test_delete_cv_history_entry_deletes_the_whole_chain():
    db = make_session()
    v1 = _cv(db)
    v2 = save_cv_version(db, parent=v1, profile_snapshot="{}", edit_source="manual")
    v3_id = save_cv_version(db, parent=v2, profile_snapshot="{}", edit_source="manual").id

    delete_cv_history_entry(entry_id=v3_id, db=db)

    assert db.query(GeneratedCV).count() == 0


def test_delete_cover_letter_history_entry_deletes_the_whole_chain():
    db = make_session()
    v1 = _cl(db)
    v2 = save_cover_letter_version(
        db, parent=v1, cover_letter_text="edited", edit_source="manual"
    )

    delete_cover_letter_history_entry(entry_id=v2.id, db=db)

    assert db.query(GeneratedCoverLetter).count() == 0


def test_bulk_delete_cvs_deletes_full_chains_not_just_listed_ids():
    db = make_session()
    v1 = _cv(db)
    v2 = save_cv_version(db, parent=v1, profile_snapshot="{}", edit_source="manual")
    other = _cv(db)

    # Only the head (v2) is passed - v1, its non-head ancestor, must still
    # be cleaned up as part of the same chain.
    result = bulk_delete_cvs(body=BulkDeleteRequest(ids=[v2.id]), db=db)

    assert result == {"deleted": 2}
    remaining = {item.id for item in db.query(GeneratedCV).all()}
    assert remaining == {other.id}


def test_bulk_delete_cover_letters_deletes_full_chains():
    db = make_session()
    v1 = _cl(db)
    v2 = save_cover_letter_version(
        db, parent=v1, cover_letter_text="edited", edit_source="manual"
    )
    other = _cl(db)

    result = bulk_delete_cover_letters(body=BulkDeleteRequest(ids=[v2.id]), db=db)

    assert result == {"deleted": 2}
    remaining = {item.id for item in db.query(GeneratedCoverLetter).all()}
    assert remaining == {other.id}
