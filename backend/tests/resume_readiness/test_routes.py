from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, GeneratedCV
from app.resume_readiness import models as readiness_models  # noqa: F401
from app.resume_readiness.domain import (
    AnalysisMode,
    AnalysisStatus,
    Category,
    CategoryResult,
    OverallResult,
    ReadinessResult,
)
from app.resume_readiness.schemas import ResumeReadinessAnalyzeRequest
from app.routes import resume_readiness as routes
from app.role_match import models as role_match_models  # noqa: F401


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _result() -> ReadinessResult:
    parseability = CategoryResult(
        category=Category.PARSEABILITY,
        raw_score=95,
        score=95,
        band="excellent",
        score_cap=None,
    )
    quality = CategoryResult(
        category=Category.QUALITY,
        raw_score=80,
        score=80,
        band="good",
        score_cap=None,
    )
    return ReadinessResult(
        mode=AnalysisMode.GENERAL,
        status=AnalysisStatus.COMPLETE,
        overall=OverallResult(
            status=AnalysisStatus.COMPLETE,
            score=88,
            band="good",
        ),
        parseability=parseability,
        quality=quality,
        tailoring=None,
        rule_results=(),
    )


def test_create_general_readiness_analysis(monkeypatch):
    db = make_session()
    try:
        cv = GeneratedCV(
            profile_snapshot='{"name":"Edo","email":"edo@example.com"}'
        )
        db.add(cv)
        db.commit()
        monkeypatch.setattr(routes, "analyze_generated_cv", lambda value: _result())

        response = routes.create_resume_readiness_analysis(
            ResumeReadinessAnalyzeRequest(generated_cv_id=cv.id),
            db,
        )

        assert response.generated_cv_id == cv.id
        assert response.mode == "general"
        assert response.categories.tailoring is None
        assert response.overall.score == 88
    finally:
        db.close()


def test_latest_legacy_cv_without_analysis_returns_404():
    db = make_session()
    try:
        cv = GeneratedCV(profile_snapshot='{"name":"Edo","email":"e@example.com"}')
        db.add(cv)
        db.commit()

        try:
            routes.read_latest_resume_readiness(cv.id, db)
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 404
        else:
            raise AssertionError("Expected HTTP 404")
    finally:
        db.close()


def test_invalid_profile_snapshot_is_persisted_as_failed():
    db = make_session()
    try:
        cv = GeneratedCV(profile_snapshot="not-json")
        db.add(cv)
        db.commit()

        response = routes.create_resume_readiness_analysis(
            ResumeReadinessAnalyzeRequest(generated_cv_id=cv.id),
            db,
        )

        assert response.status == "failed"
        assert response.failure_code == "INVALID_PROFILE_SNAPSHOT"
        assert response.overall.score is None
    finally:
        db.close()
