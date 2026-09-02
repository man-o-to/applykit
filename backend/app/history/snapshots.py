from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import GeneratedCoverLetter, GeneratedCV


def save_cv_version(
    db: Session,
    *,
    parent: GeneratedCV,
    profile_snapshot: str,
    edit_source: str,
    edit_instruction: str | None = None,
    edit_target_excerpt: str | None = None,
) -> GeneratedCV:
    """Create a new CV version derived from `parent`.

    Always INSERTs a new row - existing version rows are never mutated.
    Non-content fields are copied from the parent so each version stays a
    fully self-contained snapshot. The last step marks the parent as
    superseded, mirroring role_match/snapshots.py::save_analysis_snapshot.
    """
    version = GeneratedCV(
        enhanced=parent.enhanced,
        profile_snapshot=profile_snapshot,
        profile_id=parent.profile_id,
        application_id=parent.application_id,
        application_status=parent.application_status,
        parent_version_id=parent.id,
        edit_source=edit_source,
        edit_instruction=edit_instruction,
        edit_target_excerpt=edit_target_excerpt,
    )
    db.add(version)
    db.flush()

    parent.superseded_by_id = version.id
    db.commit()
    db.refresh(version)
    return version


def save_cover_letter_version(
    db: Session,
    *,
    parent: GeneratedCoverLetter,
    cover_letter_text: str,
    edit_source: str,
    edit_instruction: str | None = None,
    edit_target_excerpt: str | None = None,
) -> GeneratedCoverLetter:
    """Create a new cover letter version derived from `parent`. See
    save_cv_version - same insert-only, copy-then-supersede pattern."""
    version = GeneratedCoverLetter(
        company_name=parent.company_name,
        role_title=parent.role_title,
        location=parent.location,
        salary=parent.salary,
        job_description=parent.job_description,
        extra_context=parent.extra_context,
        cover_letter_text=cover_letter_text,
        profile_id=parent.profile_id,
        application_id=parent.application_id,
        job_url=parent.job_url,
        match_score=parent.match_score,
        fit_analysis=parent.fit_analysis,
        tone=parent.tone,
        application_status=parent.application_status,
        parent_version_id=parent.id,
        edit_source=edit_source,
        edit_instruction=edit_instruction,
        edit_target_excerpt=edit_target_excerpt,
    )
    # role_match_analysis_id is bolted onto GeneratedCoverLetter by
    # app.role_match.models rather than declared natively - carry it
    # forward defensively in case that module hasn't been imported yet.
    version.role_match_analysis_id = getattr(parent, "role_match_analysis_id", None)

    db.add(version)
    db.flush()

    parent.superseded_by_id = version.id
    db.commit()
    db.refresh(version)
    return version
