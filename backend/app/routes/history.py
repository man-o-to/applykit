import json
import re
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.exceptions import HistoryEntryNotFoundError, InvalidRequestError
from app.history.compare import diff_json_values, diff_text_lines
from app.history.repository import (
    delete_cl_chain,
    delete_cv_chain,
    list_cl_chain,
    list_cv_chain,
)
from app.history.snapshots import save_cover_letter_version, save_cv_version
from app.models import Application, GeneratedCoverLetter, GeneratedCV
from app.role_match.integration import enrich_cover_letter_role_match
from app.role_match.product_schemas import (
    RoleMatchGeneratedCoverLetterEntry,
    RoleMatchGeneratedCoverLetterListResponse,
)
from app.schemas import (
    BulkDeleteRequest,
    CoverLetterComparisonResponse,
    CoverLetterLineDiffEntry,
    CoverLetterManualEditRequest,
    CvComparisonResponse,
    CvFieldChange,
    CvManualEditRequest,
    DocumentVersionItem,
    DocumentVersionsResponse,
    GeneratedCVEntry,
    GeneratedCVListResponse,
    UpdateStatusRequest,
)
from app.utils import batch_load_profiles

router = APIRouter()


def _extract_company(entry: GeneratedCoverLetter) -> str:
    """Extract company name from stored field or job_description."""
    if entry.company_name:
        return entry.company_name
    first_line = re.sub(
        r"^(title|job title|position|role)\s*:\s*",
        "",
        (entry.job_description or "").split("\n")[0].strip(),
        flags=re.IGNORECASE,
    )
    at_match = re.search(r"\bat\s+([^,(\n]+)", first_line, re.IGNORECASE)
    if at_match:
        return at_match.group(1).strip()[:30]
    dash_match = re.search(r"\s[-–]\s*([A-Za-z]\S+)", first_line)
    if dash_match:
        return dash_match.group(1)[:30]
    return first_line[:30] or "Unknown Company"


def _enrich_cv(entry: GeneratedCV, profiles: dict) -> dict:
    p = profiles.get(entry.profile_id) if entry.profile_id else None
    return {
        "id": entry.id,
        "created_at": entry.created_at,
        "enhanced": bool(entry.enhanced),
        "profile_snapshot": entry.profile_snapshot,
        "application_status": entry.application_status,
        "profile_id": entry.profile_id,
        "profile_label": p.label if p else None,
        "profile_color": p.color if p else None,
        "profile_icon": p.icon if p else None,
        "parent_version_id": entry.parent_version_id,
        "superseded_by_id": entry.superseded_by_id,
        "edit_source": entry.edit_source,
        "edit_instruction": entry.edit_instruction,
    }


def _enrich_cl(entry: GeneratedCoverLetter, profiles: dict, db: Session) -> dict:
    p = profiles.get(entry.profile_id) if entry.profile_id else None
    fit = None
    if entry.fit_analysis:
        try:
            fit = json.loads(entry.fit_analysis)
        except Exception:
            fit = None
    role_match = enrich_cover_letter_role_match(db, entry)
    return {
        "id": entry.id,
        "created_at": entry.created_at,
        "company_name": entry.company_name,
        "role_title": entry.role_title,
        "location": entry.location,
        "salary": entry.salary,
        "job_description": entry.job_description,
        "extra_context": entry.extra_context,
        "cover_letter_text": entry.cover_letter_text,
        "tone": entry.tone or "professional",
        "job_url": entry.job_url,
        "fit_analysis": fit,
        "application_status": entry.application_status,
        "application_id": entry.application_id,
        "profile_id": entry.profile_id,
        "profile_label": p.label if p else None,
        "profile_color": p.color if p else None,
        "profile_icon": p.icon if p else None,
        "parent_version_id": entry.parent_version_id,
        "superseded_by_id": entry.superseded_by_id,
        "edit_source": entry.edit_source,
        "edit_instruction": entry.edit_instruction,
        **role_match,
    }


# --- CV history ---


@router.get("/history/cv", response_model=GeneratedCVListResponse)
def list_cv_history(
    db: Session = Depends(get_db),
    profile_id: int | None = Query(default=None),
    sort: str = Query(default="date_desc"),
    limit: int = Query(default=20),
    offset: int = Query(default=0),
):
    q = db.query(GeneratedCV).filter(GeneratedCV.superseded_by_id.is_(None))
    if profile_id is not None:
        q = q.filter(GeneratedCV.profile_id == profile_id)
    if sort == "date_asc":
        q = q.order_by(GeneratedCV.created_at.asc())
    else:
        q = q.order_by(GeneratedCV.created_at.desc())
    total = q.count()
    items = q.offset(offset).limit(limit).all()
    pm = batch_load_profiles(items, db)
    return GeneratedCVListResponse(
        items=[_enrich_cv(e, pm) for e in items], total=total
    )


@router.get("/history/cv/{entry_id}", response_model=GeneratedCVEntry)
def get_cv_history_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(GeneratedCV).filter_by(id=entry_id).first()
    if not entry:
        raise HistoryEntryNotFoundError("CV entry", entry_id)
    return _enrich_cv(entry, batch_load_profiles([entry], db))


@router.delete("/history/cv/{entry_id}", status_code=204)
def delete_cv_history_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(GeneratedCV).filter_by(id=entry_id).first()
    if not entry:
        raise HistoryEntryNotFoundError("CV entry", entry_id)
    delete_cv_chain(db, entry_id)


@router.patch("/history/cv/{entry_id}/status", response_model=GeneratedCVEntry)
def update_cv_status(
    entry_id: int, body: UpdateStatusRequest, db: Session = Depends(get_db)
):
    entry = db.query(GeneratedCV).filter_by(id=entry_id).first()
    if not entry:
        raise HistoryEntryNotFoundError("CV entry", entry_id)
    entry.application_status = body.status
    db.commit()
    return _enrich_cv(entry, batch_load_profiles([entry], db))


@router.post("/history/cv/{entry_id}/versions", response_model=GeneratedCVEntry)
def create_cv_version(
    entry_id: int, body: CvManualEditRequest, db: Session = Depends(get_db)
):
    parent = db.query(GeneratedCV).filter_by(id=entry_id).first()
    if not parent:
        raise HistoryEntryNotFoundError("CV entry", entry_id)
    if parent.superseded_by_id is not None:
        raise InvalidRequestError(
            "This version has already been superseded by a newer edit. Reload to see the latest version."
        )
    version = save_cv_version(
        db,
        parent=parent,
        profile_snapshot=body.profile_snapshot.model_dump_json(),
        edit_source="manual",
        edit_instruction=body.edit_note,
    )
    return _enrich_cv(version, batch_load_profiles([version], db))


@router.get("/history/cv/{entry_id}/versions", response_model=DocumentVersionsResponse)
def list_cv_versions(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(GeneratedCV).filter_by(id=entry_id).first()
    if not entry:
        raise HistoryEntryNotFoundError("CV entry", entry_id)
    chain = list_cv_chain(db, entry)
    return DocumentVersionsResponse(
        items=[
            DocumentVersionItem(
                id=item.id,
                parent_version_id=item.parent_version_id,
                superseded_by_id=item.superseded_by_id,
                created_at=item.created_at,
                edit_source=item.edit_source,
                edit_instruction=item.edit_instruction,
            )
            for item in chain
        ]
    )


@router.post(
    "/history/cv/{entry_id}/versions/{target_id}/revert",
    response_model=GeneratedCVEntry,
)
def revert_cv_version(entry_id: int, target_id: int, db: Session = Depends(get_db)):
    entry = db.query(GeneratedCV).filter_by(id=entry_id).first()
    if not entry:
        raise HistoryEntryNotFoundError("CV entry", entry_id)
    if entry.superseded_by_id is not None:
        raise InvalidRequestError(
            "This version has already been superseded by a newer edit. Reload to see the latest version."
        )
    target = db.query(GeneratedCV).filter_by(id=target_id).first()
    if not target:
        raise HistoryEntryNotFoundError("CV entry", target_id)
    chain_ids = {item.id for item in list_cv_chain(db, entry)}
    if target_id not in chain_ids:
        raise InvalidRequestError(
            "The requested version does not belong to this document's history."
        )
    version = save_cv_version(
        db,
        parent=entry,
        profile_snapshot=target.profile_snapshot,
        edit_source="restore",
        edit_instruction=f"Restored from a version created at {target.created_at.isoformat()}",
    )
    return _enrich_cv(version, batch_load_profiles([version], db))


@router.get(
    "/history/cv/{entry_id}/compare/{other_id}",
    response_model=CvComparisonResponse,
)
def compare_cv_versions(entry_id: int, other_id: int, db: Session = Depends(get_db)):
    before = db.query(GeneratedCV).filter_by(id=entry_id).first()
    if not before:
        raise HistoryEntryNotFoundError("CV entry", entry_id)
    after = db.query(GeneratedCV).filter_by(id=other_id).first()
    if not after:
        raise HistoryEntryNotFoundError("CV entry", other_id)
    changes = diff_json_values(
        json.loads(before.profile_snapshot), json.loads(after.profile_snapshot)
    )
    return CvComparisonResponse(
        from_version_id=before.id,
        to_version_id=after.id,
        changed_fields=[
            CvFieldChange(path=c["path"], from_value=c["from"], to_value=c["to"])
            for c in changes
        ],
    )


# --- Cover letter history ---


@router.get(
    "/history/cover-letter",
    response_model=RoleMatchGeneratedCoverLetterListResponse,
)
def list_cover_letter_history(
    db: Session = Depends(get_db),
    profile_id: int | None = Query(default=None),
    search: str | None = Query(default=None),
    match_min: int | None = Query(default=None),
    match_max: int | None = Query(default=None),
    status: str | None = Query(default=None),
    sort: str = Query(default="date_desc"),
    limit: int = Query(default=20),
    offset: int = Query(default=0),
):
    q = db.query(GeneratedCoverLetter).filter(
        GeneratedCoverLetter.superseded_by_id.is_(None)
    )
    if profile_id is not None:
        q = q.filter(GeneratedCoverLetter.profile_id == profile_id)
    if search:
        term = f"%{search}%"
        q = q.filter(
            GeneratedCoverLetter.company_name.ilike(term)
            | GeneratedCoverLetter.job_description.ilike(term)
        )
    if status:
        q = q.filter(GeneratedCoverLetter.application_status == status)
    if sort == "date_asc":
        q = q.order_by(GeneratedCoverLetter.created_at.asc())
    elif sort == "company_asc":
        q = q.order_by(GeneratedCoverLetter.company_name.asc().nullslast())
    else:
        q = q.order_by(GeneratedCoverLetter.created_at.desc())

    entries = q.all()
    profiles = batch_load_profiles(entries, db)
    enriched = [_enrich_cl(entry, profiles, db) for entry in entries]
    if match_min is not None:
        enriched = [
            item
            for item in enriched
            if item["match_score"] is not None and item["match_score"] >= match_min
        ]
    if match_max is not None:
        enriched = [
            item
            for item in enriched
            if item["match_score"] is not None and item["match_score"] <= match_max
        ]
    if sort == "match_desc":
        enriched.sort(
            key=lambda item: (
                item["match_score"] is not None,
                item["match_score"] or -1,
                item["created_at"],
            ),
            reverse=True,
        )

    total = len(enriched)
    page = enriched[offset : offset + limit]
    return RoleMatchGeneratedCoverLetterListResponse(items=page, total=total)


@router.get(
    "/history/cover-letter/{entry_id}",
    response_model=RoleMatchGeneratedCoverLetterEntry,
)
def get_cover_letter_history_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(GeneratedCoverLetter).filter_by(id=entry_id).first()
    if not entry:
        raise HistoryEntryNotFoundError("Cover letter", entry_id)
    return _enrich_cl(entry, batch_load_profiles([entry], db), db)


@router.delete("/history/cover-letter/{entry_id}", status_code=204)
def delete_cover_letter_history_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(GeneratedCoverLetter).filter_by(id=entry_id).first()
    if not entry:
        raise HistoryEntryNotFoundError("Cover letter", entry_id)
    delete_cl_chain(db, entry_id)


@router.patch(
    "/history/cover-letter/{entry_id}/status",
    response_model=RoleMatchGeneratedCoverLetterEntry,
)
def update_cover_letter_status(
    entry_id: int, body: UpdateStatusRequest, db: Session = Depends(get_db)
):
    entry = db.query(GeneratedCoverLetter).filter_by(id=entry_id).first()
    if not entry:
        raise HistoryEntryNotFoundError("Cover letter", entry_id)
    entry.application_status = body.status
    if body.status:
        if entry.application_id:
            linked = db.query(Application).filter_by(id=entry.application_id).first()
            if linked:
                linked.status = body.status
        else:
            app = Application(
                company_name=entry.company_name or "Unknown",
                role_title=entry.role_title or "",
                location=entry.location,
                # entry.salary is free text (e.g. "Competitive", "$120K-$150K");
                # left null here rather than guessing a structured min/max split.
                job_description=entry.job_description,
                status=body.status,
                job_url=entry.job_url,
                profile_id=entry.profile_id,
                applied_date=date.today(),
            )
            db.add(app)
            db.flush()
            entry.application_id = app.id
    db.commit()
    return _enrich_cl(entry, batch_load_profiles([entry], db), db)


@router.post(
    "/history/cover-letter/{entry_id}/versions",
    response_model=RoleMatchGeneratedCoverLetterEntry,
)
def create_cover_letter_version(
    entry_id: int, body: CoverLetterManualEditRequest, db: Session = Depends(get_db)
):
    parent = db.query(GeneratedCoverLetter).filter_by(id=entry_id).first()
    if not parent:
        raise HistoryEntryNotFoundError("Cover letter", entry_id)
    if parent.superseded_by_id is not None:
        raise InvalidRequestError(
            "This version has already been superseded by a newer edit. Reload to see the latest version."
        )
    version = save_cover_letter_version(
        db,
        parent=parent,
        cover_letter_text=body.cover_letter_text,
        edit_source="manual",
        edit_instruction=body.edit_note,
    )
    return _enrich_cl(version, batch_load_profiles([version], db), db)


@router.get(
    "/history/cover-letter/{entry_id}/versions",
    response_model=DocumentVersionsResponse,
)
def list_cover_letter_versions(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(GeneratedCoverLetter).filter_by(id=entry_id).first()
    if not entry:
        raise HistoryEntryNotFoundError("Cover letter", entry_id)
    chain = list_cl_chain(db, entry)
    return DocumentVersionsResponse(
        items=[
            DocumentVersionItem(
                id=item.id,
                parent_version_id=item.parent_version_id,
                superseded_by_id=item.superseded_by_id,
                created_at=item.created_at,
                edit_source=item.edit_source,
                edit_instruction=item.edit_instruction,
            )
            for item in chain
        ]
    )


@router.post(
    "/history/cover-letter/{entry_id}/versions/{target_id}/revert",
    response_model=RoleMatchGeneratedCoverLetterEntry,
)
def revert_cover_letter_version(
    entry_id: int, target_id: int, db: Session = Depends(get_db)
):
    entry = db.query(GeneratedCoverLetter).filter_by(id=entry_id).first()
    if not entry:
        raise HistoryEntryNotFoundError("Cover letter", entry_id)
    if entry.superseded_by_id is not None:
        raise InvalidRequestError(
            "This version has already been superseded by a newer edit. Reload to see the latest version."
        )
    target = db.query(GeneratedCoverLetter).filter_by(id=target_id).first()
    if not target:
        raise HistoryEntryNotFoundError("Cover letter", target_id)
    chain_ids = {item.id for item in list_cl_chain(db, entry)}
    if target_id not in chain_ids:
        raise InvalidRequestError(
            "The requested version does not belong to this document's history."
        )
    version = save_cover_letter_version(
        db,
        parent=entry,
        cover_letter_text=target.cover_letter_text,
        edit_source="restore",
        edit_instruction=f"Restored from a version created at {target.created_at.isoformat()}",
    )
    return _enrich_cl(version, batch_load_profiles([version], db), db)


@router.get(
    "/history/cover-letter/{entry_id}/compare/{other_id}",
    response_model=CoverLetterComparisonResponse,
)
def compare_cover_letter_versions(
    entry_id: int, other_id: int, db: Session = Depends(get_db)
):
    before = db.query(GeneratedCoverLetter).filter_by(id=entry_id).first()
    if not before:
        raise HistoryEntryNotFoundError("Cover letter", entry_id)
    after = db.query(GeneratedCoverLetter).filter_by(id=other_id).first()
    if not after:
        raise HistoryEntryNotFoundError("Cover letter", other_id)
    diff = diff_text_lines(before.cover_letter_text, after.cover_letter_text)
    return CoverLetterComparisonResponse(
        from_version_id=before.id,
        to_version_id=after.id,
        diff=[CoverLetterLineDiffEntry(**entry) for entry in diff],
    )


@router.delete("/history/cover-letter")
def bulk_delete_cover_letters(body: BulkDeleteRequest, db: Session = Depends(get_db)):
    # Chain-delete each requested entry individually rather than a single
    # IN-clause delete, so any other versions in each entry's chain (not
    # necessarily listed in body.ids) are cleaned up too.
    deleted = sum(delete_cl_chain(db, entry_id) for entry_id in body.ids)
    return {"deleted": deleted}


@router.delete("/history/cv")
def bulk_delete_cvs(body: BulkDeleteRequest, db: Session = Depends(get_db)):
    deleted = sum(delete_cv_chain(db, entry_id) for entry_id in body.ids)
    return {"deleted": deleted}
