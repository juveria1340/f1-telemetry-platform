"""Dialect-aware bulk upsert so ingestion is idempotent on both Postgres and SQLite."""

from collections.abc import Sequence
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base

BATCH_SIZE = 1000


def bulk_upsert(
    db: Session,
    model: type[Base],
    rows: Sequence[dict[str, Any]],
    conflict_cols: Sequence[str],
    update: bool = True,
) -> int:
    if not rows:
        return 0

    dialect = db.get_bind().dialect.name
    insert_fn = {"postgresql": postgresql.insert, "sqlite": sqlite.insert}.get(dialect)
    if insert_fn is None:
        raise RuntimeError(f"Unsupported database dialect: {dialect}")

    total = 0
    try:
        for start in range(0, len(rows), BATCH_SIZE):
            batch = rows[start : start + BATCH_SIZE]
            stmt = insert_fn(model).values(list(batch))
            update_cols = [c for c in batch[0] if c not in conflict_cols]
            if update and update_cols:
                stmt = stmt.on_conflict_do_update(
                    index_elements=list(conflict_cols),
                    set_={c: stmt.excluded[c] for c in update_cols},
                )
            else:
                stmt = stmt.on_conflict_do_nothing(index_elements=list(conflict_cols))
            result = db.execute(stmt)
            total += max(result.rowcount or 0, 0)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Integrity error: referenced session or driver does not exist.",
        ) from exc
    return total
