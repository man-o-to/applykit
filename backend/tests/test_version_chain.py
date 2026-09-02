from datetime import UTC, datetime, timedelta

from sqlalchemy import Column, DateTime, ForeignKey, Integer, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.services.version_chain import walk_version_chain


class _Base(DeclarativeBase):
    pass


class _Node(_Base):
    __tablename__ = "node"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    parent_version_id = Column(Integer, ForeignKey("node.id"), nullable=True)


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    _Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _add(db: Session, *, parent_id: int | None, offset_seconds: int) -> _Node:
    node = _Node(
        parent_version_id=parent_id,
        created_at=datetime.now(UTC) + timedelta(seconds=offset_seconds),
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def test_walk_version_chain_single_node():
    db = _make_session()
    a = _add(db, parent_id=None, offset_seconds=0)

    chain = walk_version_chain(db, _Node, a)

    assert [item.id for item in chain] == [a.id]


def test_walk_version_chain_linear_of_three_root_first():
    db = _make_session()
    a = _add(db, parent_id=None, offset_seconds=0)
    b = _add(db, parent_id=a.id, offset_seconds=1)
    c = _add(db, parent_id=b.id, offset_seconds=2)

    # Starting from any node in the chain returns the same full chain, root-first.
    for start in (a, b, c):
        chain = walk_version_chain(db, _Node, start)
        assert [item.id for item in chain] == [a.id, b.id, c.id]


def test_walk_version_chain_survives_a_deleted_mid_node():
    """If a mid-chain node is deleted (parent_version_id SET NULL on its
    children), the orphaned child is promoted to root of its own sub-chain
    rather than the walk crashing or looping."""
    db = _make_session()
    a = _add(db, parent_id=None, offset_seconds=0)
    b = _add(db, parent_id=a.id, offset_seconds=1)
    c = _add(db, parent_id=b.id, offset_seconds=2)

    db.delete(b)
    db.commit()
    c.parent_version_id = None  # simulates the ON DELETE SET NULL a real FK applies
    db.commit()

    chain = walk_version_chain(db, _Node, c)
    assert [item.id for item in chain] == [c.id]
