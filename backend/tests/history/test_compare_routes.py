import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.role_match.models  # noqa: F401 - registers role_match tables on Base
from app.exceptions import HistoryEntryNotFoundError
from app.models import Base, GeneratedCoverLetter, GeneratedCV
from app.routes.history import compare_cover_letter_versions, compare_cv_versions

import pytest


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _cv(db, snapshot: dict) -> GeneratedCV:
    entry = GeneratedCV(enhanced=0, profile_snapshot=json.dumps(snapshot))
    db.add(entry)
    db.commit()
    return entry


def _cl(db, text: str) -> GeneratedCoverLetter:
    entry = GeneratedCoverLetter(
        job_description="desc", cover_letter_text=text, tone="professional"
    )
    db.add(entry)
    db.commit()
    return entry


def test_compare_cv_versions_identifies_changed_nested_paths():
    db = make_session()
    before = _cv(
        db,
        {
            "name": "Jane",
            "summary": "Engineer.",
            "work_experience": [{"company": "Acme", "bullets": ["Built X"]}],
        },
    )
    after = _cv(
        db,
        {
            "name": "Jane",
            "summary": "Senior engineer.",
            "work_experience": [{"company": "Acme", "bullets": ["Built X", "Shipped Y"]}],
        },
    )

    result = compare_cv_versions(entry_id=before.id, other_id=after.id, db=db)

    assert result.from_version_id == before.id
    assert result.to_version_id == after.id
    paths = {c.path for c in result.changed_fields}
    assert "summary" in paths
    assert "work_experience[0].bullets" in paths
    assert "name" not in paths  # unchanged field must not appear


def test_compare_cv_versions_reports_added_and_removed_list_entries():
    db = make_session()
    before = _cv(db, {"projects": [{"name": "A"}]})
    after = _cv(db, {"projects": [{"name": "A"}, {"name": "B"}]})

    result = compare_cv_versions(entry_id=before.id, other_id=after.id, db=db)

    changes = {c.path: c for c in result.changed_fields}
    assert "projects[1]" in changes
    assert changes["projects[1]"].from_value is None
    assert changes["projects[1]"].to_value == {"name": "B"}


def test_compare_cv_versions_404s_for_a_missing_entry():
    db = make_session()
    cv = _cv(db, {"name": "Jane"})
    with pytest.raises(HistoryEntryNotFoundError):
        compare_cv_versions(entry_id=cv.id, other_id=999, db=db)


def test_compare_cover_letter_versions_returns_line_level_diff():
    db = make_session()
    before = _cl(db, "Dear hiring manager,\nI am excited.\nThank you.")
    after = _cl(db, "Dear hiring manager,\nI am very excited.\nThank you.")

    result = compare_cover_letter_versions(entry_id=before.id, other_id=after.id, db=db)

    assert result.from_version_id == before.id
    assert result.to_version_id == after.id
    assert len(result.diff) == 1
    entry = result.diff[0]
    assert entry.from_lines == ["I am excited."]
    assert entry.to_lines == ["I am very excited."]
    assert entry.op == "replace"


def test_compare_cover_letter_versions_across_non_adjacent_versions_in_a_chain():
    db = make_session()
    v1 = _cl(db, "line one")
    v2 = _cl(db, "line one\nline two")
    v3 = _cl(db, "line one\nline two\nline three")

    result = compare_cover_letter_versions(entry_id=v1.id, other_id=v3.id, db=db)

    added = [line for entry in result.diff for line in entry.to_lines]
    assert "line two" in added
    assert "line three" in added


def test_compare_cover_letter_versions_404s_for_a_missing_entry():
    db = make_session()
    cl = _cl(db, "text")
    with pytest.raises(HistoryEntryNotFoundError):
        compare_cover_letter_versions(entry_id=cl.id, other_id=999, db=db)
