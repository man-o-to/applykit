import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.role_match.models  # noqa: F401 - registers role_match tables on Base
from app.exceptions import HistoryEntryNotFoundError, InvalidRequestError
from app.models import Base, GeneratedCoverLetter, GeneratedCV
from app.routes.history_edit import (
    apply_cover_letter_selection_edit,
    apply_cv_selection_edit,
)
from app.schemas import (
    CoverLetterSelectionEditApplyRequest,
    CvEditTarget,
    CvSelectionEditApplyRequest,
)


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


SNAPSHOT = {
    "name": "Jane",
    "email": "jane@example.com",
    "summary": "Old summary.",
    "work_experience": [
        {"company": "Acme", "role": "Engineer", "start_date": "2020", "end_date": None, "bullets": ["Built X", "Shipped Y"]}
    ],
    "education": [],
    "skills": [],
    "projects": [],
    "certifications": [],
}


def _cv(db, snapshot: dict = SNAPSHOT) -> GeneratedCV:
    entry = GeneratedCV(enhanced=0, profile_snapshot=json.dumps(snapshot))
    db.add(entry)
    db.commit()
    return entry


def _cl(db, text: str = "I am excited about this opportunity.") -> GeneratedCoverLetter:
    entry = GeneratedCoverLetter(job_description="desc", cover_letter_text=text, tone="professional")
    db.add(entry)
    db.commit()
    return entry


def test_apply_cv_selection_edit_patches_only_the_targeted_field():
    db = make_session()
    parent = _cv(db)

    req = CvSelectionEditApplyRequest(
        target=CvEditTarget(section="work_experience", index=0, subfield="bullets"),
        new_value=["Built X better", "Shipped Y faster"],
        instruction="Make it punchier",
    )
    result = apply_cv_selection_edit(entry_id=parent.id, req=req, db=db)

    new_snapshot = json.loads(result["profile_snapshot"])
    assert new_snapshot["work_experience"][0]["bullets"] == ["Built X better", "Shipped Y faster"]
    # Everything else - including untouched fields on the same entry - is unchanged.
    assert new_snapshot["name"] == SNAPSHOT["name"]
    assert new_snapshot["email"] == SNAPSHOT["email"]
    assert new_snapshot["summary"] == SNAPSHOT["summary"]
    assert new_snapshot["work_experience"][0]["company"] == "Acme"
    assert new_snapshot["work_experience"][0]["role"] == "Engineer"
    assert new_snapshot["work_experience"][0]["start_date"] == "2020"

    assert result["edit_source"] == "ai_selection"
    assert result["edit_instruction"] == "Make it punchier"
    assert result["edit_target_excerpt"] == "Built X\nShipped Y"
    assert db.query(GeneratedCV).count() == 2


def test_apply_cv_selection_edit_on_summary():
    db = make_session()
    parent = _cv(db)

    req = CvSelectionEditApplyRequest(
        target=CvEditTarget(section="summary"),
        new_value="New, punchier summary.",
        instruction="Make it shorter",
    )
    result = apply_cv_selection_edit(entry_id=parent.id, req=req, db=db)

    new_snapshot = json.loads(result["profile_snapshot"])
    assert new_snapshot["summary"] == "New, punchier summary."
    assert result["edit_target_excerpt"] == "Old summary."


def test_apply_cv_selection_edit_404s_for_a_missing_entry():
    db = make_session()
    req = CvSelectionEditApplyRequest(
        target=CvEditTarget(section="summary"), new_value="x"
    )
    with pytest.raises(HistoryEntryNotFoundError):
        apply_cv_selection_edit(entry_id=999, req=req, db=db)


def test_apply_cv_selection_edit_rejects_a_stale_non_head_entry_id():
    db = make_session()
    parent = _cv(db)
    apply_cv_selection_edit(
        entry_id=parent.id,
        req=CvSelectionEditApplyRequest(
            target=CvEditTarget(section="summary"), new_value="v2"
        ),
        db=db,
    )

    with pytest.raises(InvalidRequestError):
        apply_cv_selection_edit(
            entry_id=parent.id,
            req=CvSelectionEditApplyRequest(
                target=CvEditTarget(section="summary"), new_value="stale edit"
            ),
            db=db,
        )


def test_apply_cv_selection_edit_rejects_an_out_of_range_index():
    db = make_session()
    parent = _cv(db)
    req = CvSelectionEditApplyRequest(
        target=CvEditTarget(section="work_experience", index=5, subfield="bullets"),
        new_value=["x"],
    )
    with pytest.raises(InvalidRequestError):
        apply_cv_selection_edit(entry_id=parent.id, req=req, db=db)


def test_apply_cv_selection_edit_rejects_a_new_value_of_the_wrong_shape():
    """bullets is a list[str] - writing a plain string must be rejected, not
    silently persisted (which would corrupt the stored JSON snapshot)."""
    db = make_session()
    parent = _cv(db)
    req = CvSelectionEditApplyRequest(
        target=CvEditTarget(section="work_experience", index=0, subfield="bullets"),
        new_value="not a list",
    )
    with pytest.raises(InvalidRequestError):
        apply_cv_selection_edit(entry_id=parent.id, req=req, db=db)


def test_apply_cv_selection_edit_rejects_a_non_field_subfield():
    """Only real declared model fields are addressable - not arbitrary
    attributes like dunder/internal Pydantic machinery."""
    db = make_session()
    parent = _cv(db)
    req = CvSelectionEditApplyRequest(
        target=CvEditTarget(section="work_experience", index=0, subfield="__class__"),
        new_value="whatever",
    )
    with pytest.raises(InvalidRequestError):
        apply_cv_selection_edit(entry_id=parent.id, req=req, db=db)


def test_apply_cover_letter_selection_edit_patches_only_the_selected_range():
    db = make_session()
    parent = _cl(db, "I am excited about this opportunity.")

    req = CoverLetterSelectionEditApplyRequest(
        selection_start=5,
        selection_end=12,
        excerpt="excited",
        new_value="thrilled",
        instruction="More enthusiastic",
    )
    result = apply_cover_letter_selection_edit(entry_id=parent.id, req=req, db=db)

    assert result["cover_letter_text"] == "I am thrilled about this opportunity."
    assert result["edit_source"] == "ai_selection"
    assert result["edit_target_excerpt"] == "excited"
    assert db.query(GeneratedCoverLetter).count() == 2


def test_apply_cover_letter_selection_edit_rejects_drifted_selection():
    db = make_session()
    parent = _cl(db, "I am excited about this opportunity.")

    req = CoverLetterSelectionEditApplyRequest(
        selection_start=5,
        selection_end=12,
        excerpt="wrong text",  # doesn't match cover_letter_text[5:12]
        new_value="thrilled",
    )
    with pytest.raises(InvalidRequestError):
        apply_cover_letter_selection_edit(entry_id=parent.id, req=req, db=db)


def test_apply_cover_letter_selection_edit_404s_for_a_missing_entry():
    db = make_session()
    req = CoverLetterSelectionEditApplyRequest(
        selection_start=0, selection_end=1, excerpt="x", new_value="y"
    )
    with pytest.raises(HistoryEntryNotFoundError):
        apply_cover_letter_selection_edit(entry_id=999, req=req, db=db)


def test_apply_cover_letter_selection_edit_rejects_a_stale_non_head_entry_id():
    db = make_session()
    parent = _cl(db, "I am excited.")
    apply_cover_letter_selection_edit(
        entry_id=parent.id,
        req=CoverLetterSelectionEditApplyRequest(
            selection_start=0, selection_end=1, excerpt="I", new_value="We"
        ),
        db=db,
    )

    with pytest.raises(InvalidRequestError):
        apply_cover_letter_selection_edit(
            entry_id=parent.id,
            req=CoverLetterSelectionEditApplyRequest(
                selection_start=0, selection_end=1, excerpt="I", new_value="stale"
            ),
            db=db,
        )
