"""
WeCare — Read-only Database Inspector (STEP 11)

Connects to the live MySQL database and prints a summary of all tables,
columns, indexes, and foreign keys. Does NOT modify anything.

Usage:
    python -m scripts.inspect_database
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect, text
from app.core.config import get_settings


def main():
    settings = get_settings()
    print(f"Connecting to: {settings.DB_HOST}:{settings.DB_PORT}/{settings.database_name}")
    print(f"Environment: {settings.APP_ENV}")
    print("=" * 70)

    engine = create_engine(settings.database_url, echo=False)

    try:
        with engine.connect() as conn:
            # Verify connection
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
            print("✓ Database connection successful\n")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        sys.exit(1)

    inspector = inspect(engine)
    table_names = sorted(inspector.get_table_names())

    print(f"Tables found: {len(table_names)}\n")

    for table_name in table_names:
        columns = inspector.get_columns(table_name)
        pk = inspector.get_pk_constraint(table_name)
        fks = inspector.get_foreign_keys(table_name)
        indexes = inspector.get_indexes(table_name)
        uniques = inspector.get_unique_constraints(table_name)

        print(f"── {table_name} ({len(columns)} columns) ──")

        # Primary key
        pk_cols = pk.get("constrained_columns", [])
        if pk_cols:
            print(f"  PK: {', '.join(pk_cols)}")

        # Columns
        for col in columns:
            nullable = "NULL" if col.get("nullable") else "NOT NULL"
            default = col.get("default", "")
            default_str = f" DEFAULT {default}" if default else ""
            print(f"  - {col['name']}: {col['type']} {nullable}{default_str}")

        # Foreign keys
        if fks:
            print(f"  Foreign Keys ({len(fks)}):")
            for fk in fks:
                ref_table = fk["referred_table"]
                ref_cols = fk["referred_columns"]
                local_cols = fk["constrained_columns"]
                print(f"    {', '.join(local_cols)} → {ref_table}({', '.join(ref_cols)})")

        # Indexes
        if indexes:
            print(f"  Indexes ({len(indexes)}):")
            for idx in indexes:
                unique_flag = " UNIQUE" if idx.get("unique") else ""
                print(f"    {idx['name']}: ({', '.join(idx['column_names'])}){unique_flag}")

        print()

    print(f"\nTotal: {len(table_names)} tables inspected (read-only)")
    engine.dispose()


if __name__ == "__main__":
    main()
