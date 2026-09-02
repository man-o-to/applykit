from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.history.snapshots import save_cover_letter_version, save_cv_version
from app.models import Base, GeneratedCoverLetter, GeneratedCV


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _cv(**overrides) -> GeneratedCV:
    base = dict(
        enhanced=1,
        profile_snapshot='{"name": "Jane"}',
        profile_id=1,
        application_id=None,
        application_status=None,
    )
    base.update(overrides)
    return GeneratedCV(**base)


def _cl(**overrides) -> GeneratedCoverLetter:
    base = dict(
        company_name="Acme",
        role_title="Engineer",
        location="Remote",
        salary="$120K",
        job_description="Build things",
        extra_context="Be concise",
        cover_letter_text="Dear hiring manager,",
        profile_id=1,
        application_id=None,
        job_url="https://example.com/job",
        match_score=80,
        fit_analysis=None,
        tone="professional",
        application_status=None,
    )
    base.update(overrides)
    return GeneratedCoverLetter(**base)


def test_save_cv_version_inserts_a_new_row_and_never_mutates_the_parent():
    db = make_session()
    parent = _cv()
    db.add(parent)
    db.commit()

    version = save_cv_version(
        db,
        parent=parent,
        profile_snapshot='{"name": "Jane", "summary": "edited"}',
        edit_source="manual",
    )

    assert version.id != parent.id
    assert version.profile_snapshot == '{"name": "Jane", "summary": "edited"}'
    # The parent row's own content is untouched.
    assert parent.profile_snapshot == '{"name": "Jane"}'
    assert db.query(GeneratedCV).count() == 2


def test_save_cv_version_sets_parent_superseded_by_id():
    db = make_session()
    parent = _cv()
    db.add(parent)
    db.commit()

    version = save_cv_version(
        db, parent=parent, profile_snapshot="{}", edit_source="manual"
    )

    assert parent.superseded_by_id == version.id
    assert version.parent_version_id == parent.id


def test_save_cv_version_copies_non_content_fields_from_parent():
    db = make_session()
    parent = _cv(enhanced=1, profile_id=7, application_id=3, application_status="applied")
    db.add(parent)
    db.commit()

    version = save_cv_version(
        db, parent=parent, profile_snapshot="{}", edit_source="ai_selection", edit_instruction="shorten it"
    )

    assert version.enhanced == parent.enhanced
    assert version.profile_id == parent.profile_id
    assert version.application_id == parent.application_id
    assert version.application_status == parent.application_status
    assert version.edit_source == "ai_selection"
    assert version.edit_instruction == "shorten it"


def test_save_cover_letter_version_inserts_a_new_row_and_never_mutates_the_parent():
    db = make_session()
    parent = _cl()
    db.add(parent)
    db.commit()

    version = save_cover_letter_version(
        db,
        parent=parent,
        cover_letter_text="Dear hiring manager, edited.",
        edit_source="manual",
    )

    assert version.id != parent.id
    assert version.cover_letter_text == "Dear hiring manager, edited."
    assert parent.cover_letter_text == "Dear hiring manager,"
    assert db.query(GeneratedCoverLetter).count() == 2


def test_save_cover_letter_version_sets_parent_superseded_by_id():
    db = make_session()
    parent = _cl()
    db.add(parent)
    db.commit()

    version = save_cover_letter_version(
        db, parent=parent, cover_letter_text="edited", edit_source="manual"
    )

    assert parent.superseded_by_id == version.id
    assert version.parent_version_id == parent.id


def test_save_cover_letter_version_copies_non_content_fields_from_parent():
    db = make_session()
    parent = _cl(company_name="Acme", role_title="Engineer", tone="enthusiastic")
    db.add(parent)
    db.commit()

    version = save_cover_letter_version(
        db, parent=parent, cover_letter_text="edited", edit_source="restore"
    )

    assert version.company_name == "Acme"
    assert version.role_title == "Engineer"
    assert version.tone == "enthusiastic"
    assert version.edit_source == "restore"


def test_repeated_edits_form_a_linear_chain():
    db = make_session()
    v1 = _cv()
    db.add(v1)
    db.commit()

    v2 = save_cv_version(db, parent=v1, profile_snapshot="{}", edit_source="manual")
    v3 = save_cv_version(db, parent=v2, profile_snapshot="{}", edit_source="manual")

    assert v1.superseded_by_id == v2.id
    assert v2.superseded_by_id == v3.id
    assert v3.superseded_by_id is None
    assert v3.parent_version_id == v2.id
    assert v2.parent_version_id == v1.id
