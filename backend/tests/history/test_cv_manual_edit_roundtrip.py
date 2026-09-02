import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.role_match.models  # noqa: F401 - registers role_match tables on Base
from app.models import Base, GeneratedCV
from app.routes.history import create_cv_version
from app.schemas import (
    CvManualEditRequest,
    Education,
    Project,
    ProfileData,
    SkillCategory,
    WorkExperience,
)


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _cv(db, **overrides) -> GeneratedCV:
    base = dict(enhanced=0, profile_snapshot="{}")
    base.update(overrides)
    entry = GeneratedCV(**base)
    db.add(entry)
    db.commit()
    return entry


def full_profile() -> ProfileData:
    return ProfileData(
        label="Default",
        color="#6366f1",
        icon="💼",
        name="Jane Doe",
        email="jane@example.com",
        phone="555-0100",
        location="Remote",
        linkedin="https://linkedin.com/in/janedoe",
        github=["https://github.com/janedoe", "https://github.com/jane-work"],
        portfolio="https://jane.dev",
        summary="Backend engineer.",
        work_experience=[
            WorkExperience(
                company="Acme",
                role="Engineer",
                start_date="2020",
                end_date="2023",
                bullets=["Built X", "Shipped Y"],
            )
        ],
        education=[
            Education(
                institution="State University",
                degree="BS",
                field="Computer Science",
                start_date="2016",
                end_date="2020",
                accomplishments=["Dean's list"],
            )
        ],
        skills=["Python", "SQL"],
        skill_categories=[SkillCategory(label="Languages", skills=["Python", "SQL"])],
        projects=[
            Project(
                name="Side Project",
                description="A thing I built.",
                tech_stack=["Python"],
                link="https://github.com/janedoe/thing",
            )
        ],
        certifications=[],
    )


def test_full_profile_round_trips_through_create_version_with_no_field_loss():
    db = make_session()
    parent = _cv(db)
    profile = full_profile()

    result = create_cv_version(
        entry_id=parent.id,
        body=CvManualEditRequest(profile_snapshot=profile),
        db=db,
    )

    stored = json.loads(result["profile_snapshot"])
    expected = json.loads(profile.model_dump_json())
    assert stored == expected
