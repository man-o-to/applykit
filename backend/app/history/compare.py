from __future__ import annotations

import difflib
from typing import Any


def diff_json_values(before: Any, after: Any) -> list[dict[str, Any]]:
    """Flatten the structural differences between two JSON-compatible values
    into a list of {path, from, to} entries.

    Dicts are recursed into per key. Lists of objects are recursed into per
    index (added/removed trailing entries show up as a change against None).
    Anything else - primitives, and lists of primitives - is compared as a
    single value, since diffing reordered scalars isn't meaningfully more
    useful than just showing the whole list changed.
    """
    changes: list[dict[str, Any]] = []
    _diff(before, after, "", changes)
    return changes


def _diff(before: Any, after: Any, path: str, changes: list[dict[str, Any]]) -> None:
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            child_path = f"{path}.{key}" if path else key
            _diff(before.get(key), after.get(key), child_path, changes)
        return
    if (
        isinstance(before, list)
        and isinstance(after, list)
        and (not before or isinstance(before[0], dict))
        and (not after or isinstance(after[0], dict))
    ):
        for i in range(max(len(before), len(after))):
            item_before = before[i] if i < len(before) else None
            item_after = after[i] if i < len(after) else None
            _diff(item_before, item_after, f"{path}[{i}]", changes)
        return
    if before != after:
        changes.append({"path": path, "from": before, "to": after})


def diff_text_lines(before: str, after: str) -> list[dict[str, Any]]:
    """Line-level diff between two blocks of text, skipping unchanged runs."""
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    matcher = difflib.SequenceMatcher(None, before_lines, after_lines)
    entries: list[dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        entries.append(
            {
                "op": tag,
                "from_lines": before_lines[i1:i2],
                "to_lines": after_lines[j1:j2],
            }
        )
    return entries
