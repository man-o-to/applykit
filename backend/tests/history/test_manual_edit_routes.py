import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.role_match.models  # noqa: F401 - registers role_match tables on Base
from app.exceptions import HistoryEntryNotFoundError, InvalidRequestError
from app.models import Base, GeneratedCoverLetter, GeneratedCV
from app.routes.history import (
    create_cover_letter_version,
    create_cv_version,
    list_cover_letter_versions,
    list_cv_versions,
    revert_cover_letter_version,
    revert_cv_version,
)
from app.schemas import CoverLetterManualEditRequest, CvManualEditRequest, ProfileData


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _cv(db, **overrides) -> GeneratedCV:
    base = dict(enhanced=0, profile_snapshot='{"name": "Jane", "email": "jane@example.com"}')
    base.update(overrides)
    entry = GeneratedCV(**base)
    db.add(entry)
    db.commit()
    return entry


def _cl(db, **overrides) -> GeneratedCoverLetter:
    base = dict(job_description="desc", cover_letter_text="Dear hiring manager,", tone="professional")
    base.update(overrides)
    entry = GeneratedCoverLetter(**base)
    db.add(entry)
    db.commit()
    return entry


def _profile(**overrides) -> ProfileData:
    base = dict(name="Jane Doe", email="jane@example.com")
    base.update(overrides)
    return ProfileData(**base)


def test_create_cv_version_inserts_and_supersedes_the_parent():
    db = make_session()
    parent = _cv(db)

    result = create_cv_version(
        entry_id=parent.id,
        body=CvManualEditRequest(profile_snapshot=_profile(summary="Edited"), edit_note="fixed typo"),
        db=db,
    )

    assert result["id"] != parent.id
    assert '"summary":"Edited"' in result["profile_snapshot"].replace(" ", "")
    assert db.query(GeneratedCV).count() == 2

    # The old head is no longer returned by list, only the new one is.
    versions = list_cv_versions(entry_id=result["id"], db=db)
    assert [item.id for item in versions.items] == [parent.id, result["id"]]


def test_create_cv_version_404s_for_a_nonexistent_parent():
    db = make_session()
    with pytest.raises(HistoryEntryNotFoundError):
        create_cv_version(
            entry_id=999,
            body=CvManualEditRequest(profile_snapshot=_profile()),
            db=db,
        )


def test_create_cv_version_rejects_a_stale_non_head_entry_id():
    db = make_session()
    v1 = _cv(db)
    create_cv_version(
        entry_id=v1.id,
        body=CvManualEditRequest(profile_snapshot=_profile(summary="v2")),
        db=db,
    )

    # v1 is no longer the head - editing it again must not fork the chain.
    with pytest.raises(InvalidRequestError):
        create_cv_version(
            entry_id=v1.id,
            body=CvManualEditRequest(profile_snapshot=_profile(summary="stale edit")),
            db=db,
        )


def test_revert_cv_version_creates_a_new_version_never_mutates_existing_rows():
    db = make_session()
    v1 = _cv(db, profile_snapshot='{"name": "v1"}')
    v2_id = create_cv_version(
        entry_id=v1.id,
        body=CvManualEditRequest(profile_snapshot=_profile(summary="v2")),
        db=db,
    )["id"]

    result = revert_cv_version(entry_id=v2_id, target_id=v1.id, db=db)

    assert result["id"] not in (v1.id, v2_id)
    assert result["edit_source"] == "restore"
    assert result["profile_snapshot"] == v1.profile_snapshot
    assert db.query(GeneratedCV).count() == 3
    # v1's own row is untouched.
    original = db.query(GeneratedCV).filter_by(id=v1.id).first()
    assert original.profile_snapshot == '{"name": "v1"}'


def test_revert_cv_version_rejects_a_target_outside_the_chain():
    db = make_session()
    v1 = _cv(db)
    unrelated = _cv(db)

    with pytest.raises(InvalidRequestError):
        revert_cv_version(entry_id=v1.id, target_id=unrelated.id, db=db)


def test_revert_cv_version_rejects_a_stale_non_head_entry_id():
    db = make_session()
    v1 = _cv(db)
    v2_id = create_cv_version(
        entry_id=v1.id,
        body=CvManualEditRequest(profile_snapshot=_profile(summary="v2")),
        db=db,
    )["id"]
    create_cv_version(
        entry_id=v2_id,
        body=CvManualEditRequest(profile_snapshot=_profile(summary="v3")),
        db=db,
    )

    # v2 is no longer the head - reverting from it must not fork the chain.
    with pytest.raises(InvalidRequestError):
        revert_cv_version(entry_id=v2_id, target_id=v1.id, db=db)


def test_create_cover_letter_version_inserts_and_supersedes_the_parent():
    db = make_session()
    parent = _cl(db, cover_letter_text="Original text")

    result = create_cover_letter_version(
        entry_id=parent.id,
        body=CoverLetterManualEditRequest(cover_letter_text="Edited text", edit_note="tightened it up"),
        db=db,
    )

    assert result["id"] != parent.id
    assert result["cover_letter_text"] == "Edited text"
    assert result["edit_instruction"] == "tightened it up"
    assert db.query(GeneratedCoverLetter).count() == 2

    versions = list_cover_letter_versions(entry_id=result["id"], db=db)
    assert [item.id for item in versions.items] == [parent.id, result["id"]]


def test_create_cover_letter_version_404s_for_a_nonexistent_parent():
    db = make_session()
    with pytest.raises(HistoryEntryNotFoundError):
        create_cover_letter_version(
            entry_id=999,
            body=CoverLetterManualEditRequest(cover_letter_text="text"),
            db=db,
        )


def test_create_cover_letter_version_rejects_a_stale_non_head_entry_id():
    db = make_session()
    v1 = _cl(db, cover_letter_text="v1 text")
    create_cover_letter_version(
        entry_id=v1.id,
        body=CoverLetterManualEditRequest(cover_letter_text="v2 text"),
        db=db,
    )

    with pytest.raises(InvalidRequestError):
        create_cover_letter_version(
            entry_id=v1.id,
            body=CoverLetterManualEditRequest(cover_letter_text="stale edit"),
            db=db,
        )


def test_revert_cover_letter_version_creates_a_new_version():
    db = make_session()
    v1 = _cl(db, cover_letter_text="v1 text")
    v2_id = create_cover_letter_version(
        entry_id=v1.id,
        body=CoverLetterManualEditRequest(cover_letter_text="v2 text"),
        db=db,
    )["id"]

    result = revert_cover_letter_version(entry_id=v2_id, target_id=v1.id, db=db)

    assert result["id"] not in (v1.id, v2_id)
    assert result["edit_source"] == "restore"
    assert result["cover_letter_text"] == "v1 text"
    assert db.query(GeneratedCoverLetter).count() == 3


def test_revert_cover_letter_version_rejects_a_target_outside_the_chain():
    db = make_session()
    v1 = _cl(db)
    unrelated = _cl(db)

    with pytest.raises(InvalidRequestError):
        revert_cover_letter_version(entry_id=v1.id, target_id=unrelated.id, db=db)


def test_revert_cover_letter_version_rejects_a_stale_non_head_entry_id():
    db = make_session()
    v1 = _cl(db, cover_letter_text="v1 text")
    v2_id = create_cover_letter_version(
        entry_id=v1.id,
        body=CoverLetterManualEditRequest(cover_letter_text="v2 text"),
        db=db,
    )["id"]
    create_cover_letter_version(
        entry_id=v2_id,
        body=CoverLetterManualEditRequest(cover_letter_text="v3 text"),
        db=db,
    )

    with pytest.raises(InvalidRequestError):
        revert_cover_letter_version(entry_id=v2_id, target_id=v1.id, db=db)
