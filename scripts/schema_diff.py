"""
WeCare — Schema Diff Tool (STEP 12)

Compares SQLAlchemy model metadata against the live database schema.
Reports missing tables, missing columns, type mismatches, and missing indexes.

Usage:
    python -m scripts.schema_diff
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect
from app.core.config import get_settings
from app.core.database import Base

# Import all models to populate Base.metadata
import app.models  # noqa: F401


def main():
    settings = get_settings()
    print(f"Schema Diff: Models vs {settings.DB_HOST}:{settings.DB_PORT}/{settings.database_name}")
    print("=" * 70)

    engine = create_engine(settings.database_url, echo=False)
    inspector = inspect(engine)

    db_tables = set(inspector.get_table_names())
    model_tables = set(Base.metadata.tables.keys())

    issues = []

    # ── Tables in models but not in DB ──
    missing_in_db = model_tables - db_tables
    if missing_in_db:
        for t in sorted(missing_in_db):
            issues.append(f"TABLE MISSING IN DB: {t}")

    # ── Tables in DB but not in models ──
    extra_in_db = db_tables - model_tables
    if extra_in_db:
        for t in sorted(extra_in_db):
            issues.append(f"TABLE NOT IN MODELS: {t}")

    # ── Column-level comparison for shared tables ──
    shared_tables = model_tables & db_tables
    for table_name in sorted(shared_tables):
        model_table = Base.metadata.tables[table_name]
        db_columns = {c["name"]: c for c in inspector.get_columns(table_name)}
        model_columns = {c.name: c for c in model_table.columns}

        # Columns in model but not in DB
        for col_name in sorted(model_columns.keys() - db_columns.keys()):
            issues.append(f"  {table_name}.{col_name}: IN MODEL, MISSING IN DB")

        # Columns in DB but not in model
        for col_name in sorted(db_columns.keys() - model_columns.keys()):
            issues.append(f"  {table_name}.{col_name}: IN DB, MISSING IN MODEL")

        # Type comparison for shared columns
        for col_name in sorted(model_columns.keys() & db_columns.keys()):
            model_col = model_columns[col_name]
            db_col = db_columns[col_name]

            # Nullable mismatch
            model_nullable = model_col.nullable if model_col.nullable is not None else True
            db_nullable = db_col.get("nullable", True)
            if model_nullable != db_nullable:
                issues.append(
                    f"  {table_name}.{col_name}: nullable mismatch "
                    f"(model={model_nullable}, db={db_nullable})"
                )

    # ── Index comparison ──
    for table_name in sorted(shared_tables):
        model_table = Base.metadata.tables[table_name]
        db_indexes = inspector.get_indexes(table_name)
        db_index_names = {idx["name"] for idx in db_indexes}
        model_index_names = {idx.name for idx in model_table.indexes if idx.name}

        missing_indexes = model_index_names - db_index_names
        for idx_name in sorted(missing_indexes):
            issues.append(f"  {table_name}: INDEX {idx_name} IN MODEL, MISSING IN DB")

    # ── Report ──
    if issues:
        print(f"\n⚠ {len(issues)} differences found:\n")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("\n✓ Models and database schema are in sync!")

    print(f"\nModel tables: {len(model_tables)}")
    print(f"Database tables: {len(db_tables)}")
    print(f"Shared tables: {len(shared_tables)}")

    engine.dispose()
    return len(issues)


if __name__ == "__main__":
    exit_code = main()
    sys.exit(1 if exit_code > 0 else 0)
