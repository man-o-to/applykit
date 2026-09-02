from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter, ValidationError

from app.exceptions import InvalidRequestError
from app.schemas import CvEditTarget, ProfileData

_TARGET_NOT_FOUND = "The requested edit target does not exist in this document."
_TYPE_MISMATCH = "The new value does not match the expected shape for this field."


def get_cv_target_value(profile: ProfileData, target: CvEditTarget) -> Any:
    """Read the current value addressed by `target` out of a CV profile."""
    if target.section == "summary":
        return profile.summary
    entries = getattr(profile, target.section)
    entry = _entry_at(entries, target.index)
    if target.subfield is None:
        return entry
    _check_subfield(entry, target.subfield)
    return getattr(entry, target.subfield)


def set_cv_target_value(profile: ProfileData, target: CvEditTarget, new_value: Any) -> None:
    """Write `new_value` into the location addressed by `target`, in place.

    `new_value` is validated against the target field's declared type before
    it's written - ProfileData doesn't validate on plain attribute
    assignment, so an unvalidated write could corrupt the stored JSON
    snapshot (e.g. writing a string into a `list[str]` bullets field) in a
    way that breaks loading this document the next time it's opened.
    """
    if target.section == "summary":
        profile.summary = _validated(ProfileData.model_fields["summary"], new_value)
        return
    entries = getattr(profile, target.section)
    entry = _entry_at(entries, target.index)
    if target.subfield is None:
        raise InvalidRequestError(
            "Replacing a whole entry is not supported yet - target a specific subfield."
        )
    _check_subfield(entry, target.subfield)
    field_info = type(entry).model_fields[target.subfield]
    setattr(entry, target.subfield, _validated(field_info, new_value))


def _entry_at(entries: list, index: int | None):
    if index is None or not (0 <= index < len(entries)):
        raise InvalidRequestError(_TARGET_NOT_FOUND)
    return entries[index]


def _check_subfield(entry, subfield: str) -> None:
    # Only real declared model fields are addressable - never arbitrary
    # attributes (dunder/internal Pydantic machinery included).
    if subfield not in type(entry).model_fields:
        raise InvalidRequestError(_TARGET_NOT_FOUND)


def _validated(field_info, new_value: Any) -> Any:
    try:
        return TypeAdapter(field_info.annotation).validate_python(new_value)
    except ValidationError as exc:
        raise InvalidRequestError(_TYPE_MISMATCH) from exc
