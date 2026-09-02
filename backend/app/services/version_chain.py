from __future__ import annotations

from typing import TypeVar

from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


def walk_version_chain(
    db: Session,
    model: type[ModelT],
    start: ModelT,
    *,
    parent_col: str = "parent_version_id",
) -> list[ModelT]:
    """Return every version in the chain containing `start`, root-first.

    Walks `parent_col` backward from `start` to find the chain's root, then
    does a breadth-first walk forward (`parent_col == current.id` lookups) to
    collect every version. No "is_current"/"is_root" flag is needed anywhere:
    the root is whichever row has `parent_col` set to None, and the head is
    whichever row nothing else points back to.
    """
    root = start
    seen: set = set()
    while getattr(root, parent_col) is not None and root.id not in seen:
        seen.add(root.id)
        parent = db.query(model).filter_by(id=getattr(root, parent_col)).first()
        if parent is None:
            break
        root = parent

    items: list[ModelT] = []
    frontier = [root]
    while frontier:
        current = frontier.pop(0)
        items.append(current)
        frontier.extend(
            db.query(model)
            .filter_by(**{parent_col: current.id})
            .order_by(model.created_at.asc())
            .all()
        )
    return items
