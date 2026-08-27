"""
WeCare FastAPI — Transaction and Row-Locking Utilities

equivalent patterns:
  $conn->beginTransaction();
  try {
      $stmt = $conn->prepare("SELECT ... FOR UPDATE");
      ...
      $conn->commit();
  } catch (Exception $e) {
      $conn->rollBack();
      throw $e;
  }

STEPS 8 + 9: Transaction context manager + SELECT ... FOR UPDATE helper.
"""

from contextlib import contextmanager
from typing import Any, Generator

from sqlalchemy import text
from sqlalchemy.orm import Session


@contextmanager
def transaction(db: Session) -> Generator[Session, None, None]:
    """
    Context manager that wraps a block in a database transaction.

    $conn->beginTransaction();
        try { ... $conn->commit(); }
        catch (Exception $e) { $conn->rollBack(); throw $e; }

    Usage:
        with transaction(db) as session:
            session.execute(...)
            session.execute(...)
        # auto-committed on success, auto-rolled-back on exception
    """
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise


def select_for_update(
    db: Session,
    query: str,
    params: dict[str, Any] | list[Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Execute a SELECT ... FOR UPDATE query and return results as dicts.

    $stmt = $conn->prepare("SELECT ... FOR UPDATE");
        $stmt->execute([...]);
        $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);

    IMPORTANT: Must be called within a transaction() context.

    Args:
        db: SQLAlchemy session (must be inside a transaction)
        query: Raw SQL string containing FOR UPDATE
        params: Query parameters (dict for named params, list for positional)

    Returns:
        List of row dictionaries
    """
    if params is None:
        params = {}
    result = db.execute(text(query), params)
    columns = result.keys()
    return [dict(zip(columns, row)) for row in result.fetchall()]


def select_for_update_one(
    db: Session,
    query: str,
    params: dict[str, Any] | list[Any] | None = None,
) -> dict[str, Any] | None:
    """
    Execute a SELECT ... FOR UPDATE query and return a single row or None.

    $stmt = $conn->prepare("SELECT ... FOR UPDATE");
        $stmt->execute([...]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);
    """
    rows = select_for_update(db, query, params)
    return rows[0] if rows else None
