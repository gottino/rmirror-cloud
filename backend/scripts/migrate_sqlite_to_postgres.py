"""
Migrate data from SQLite to PostgreSQL.

This script migrates all data from the production SQLite database to PostgreSQL.
Run this after setting up the PostgreSQL database and user.

Usage:
    python scripts/migrate_sqlite_to_postgres.py --sqlite-path /path/to/rmirror.db --postgres-url postgresql://user:pass@host/db
"""

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker


def get_table_order():
    """Return tables in dependency order (parents before children)."""
    return [
        "alembic_version",
        "users",
        "notebooks",
        "pages",
        "connectors",
        "processing_jobs",
        "sync_events",
        "todos",
        "waitlist",
    ]


def migrate_table(sqlite_engine, postgres_engine, table_name):
    """Migrate a single table from SQLite to PostgreSQL."""
    print(f"Migrating table: {table_name}")

    # Check if table exists in SQLite
    inspector = inspect(sqlite_engine)
    if table_name not in inspector.get_table_names():
        print(f"  ⊘ Table {table_name} does not exist in SQLite, skipping")
        return 0

    # Check if table exists in PostgreSQL
    pg_inspector = inspect(postgres_engine)
    if table_name not in pg_inspector.get_table_names():
        print(f"  ⊘ Table {table_name} does not exist in PostgreSQL, skipping")
        return 0

    # Get column names
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    columns_str = ", ".join(f'"{col}"' for col in columns)

    # Read from SQLite
    with sqlite_engine.connect() as sqlite_conn:
        result = sqlite_conn.execute(text(f'SELECT {columns_str} FROM "{table_name}"'))
        rows = result.fetchall()

        if not rows:
            print(f"  ✓ Table {table_name} is empty")
            return 0

        # Insert into PostgreSQL
        with postgres_engine.connect() as pg_conn:
            # Clear existing data
            pg_conn.execute(text(f'DELETE FROM "{table_name}"'))
            pg_conn.commit()

            # Prepare insert statement
            placeholders = ", ".join(f":{col}" for col in columns)
            insert_sql = f'INSERT INTO "{table_name}" ({columns_str}) VALUES ({placeholders})'

            # Insert rows
            for row in rows:
                row_dict = dict(zip(columns, row))

                # Convert SQLite integers to PostgreSQL booleans
                # SQLite stores booleans as 0/1, PostgreSQL needs True/False
                for key, value in row_dict.items():
                    if isinstance(value, int) and value in (0, 1):
                        # Check if this column is a boolean type in PostgreSQL
                        pg_columns = pg_inspector.get_columns(table_name)
                        for col in pg_columns:
                            if col['name'] == key and str(col['type']).lower() == 'boolean':
                                row_dict[key] = bool(value)
                                break

                pg_conn.execute(text(insert_sql), row_dict)

            pg_conn.commit()

        print(f"  ✓ Migrated {len(rows)} rows")
        return len(rows)


def reset_sequences(postgres_engine):
    """Reset PostgreSQL sequences to match the max ID in each table."""
    print("\nResetting PostgreSQL sequences...")

    tables_with_ids = ["users", "notebooks", "pages", "connectors", "processing_jobs", "sync_events", "todos", "waitlist"]

    with postgres_engine.connect() as conn:
        inspector = inspect(postgres_engine)

        for table_name in tables_with_ids:
            if table_name not in inspector.get_table_names():
                continue

            # Get max ID
            result = conn.execute(text(f'SELECT MAX(id) FROM "{table_name}"'))
            max_id = result.scalar()

            if max_id is not None:
                # Reset sequence
                sequence_name = f"{table_name}_id_seq"
                conn.execute(text(f"SELECT setval('{sequence_name}', {max_id}, true)"))
                print(f"  ✓ Reset {sequence_name} to {max_id}")

        conn.commit()


def verify_migration(sqlite_engine, postgres_engine):
    """Verify that the migration was successful by comparing row counts."""
    print("\nVerifying migration...")

    inspector = inspect(sqlite_engine)
    tables = inspector.get_table_names()

    all_match = True

    for table_name in tables:
        with sqlite_engine.connect() as sqlite_conn:
            sqlite_count = sqlite_conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()

        with postgres_engine.connect() as pg_conn:
            try:
                pg_count = pg_conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
            except Exception:
                pg_count = 0

        if sqlite_count == pg_count:
            print(f"  ✓ {table_name}: {sqlite_count} rows")
        else:
            print(f"  ✗ {table_name}: SQLite has {sqlite_count} rows, PostgreSQL has {pg_count} rows")
            all_match = False

    return all_match


def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite database to PostgreSQL")
    parser.add_argument("--sqlite-path", required=True, help="Path to SQLite database file")
    parser.add_argument("--postgres-url", required=True, help="PostgreSQL connection URL")
    parser.add_argument("--skip-verification", action="store_true", help="Skip verification step")

    args = parser.parse_args()

    # Validate SQLite path
    sqlite_path = Path(args.sqlite_path)
    if not sqlite_path.exists():
        print(f"Error: SQLite database not found at {sqlite_path}")
        sys.exit(1)

    print(f"Migration started:")
    print(f"  Source: {sqlite_path}")
    print(f"  Target: {args.postgres_url.split('@')[1] if '@' in args.postgres_url else 'PostgreSQL'}")
    print()

    # Create engines
    sqlite_engine = create_engine(f"sqlite:///{sqlite_path}")
    postgres_engine = create_engine(args.postgres_url)

    # Test connections
    try:
        with sqlite_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✓ SQLite connection successful")
    except Exception as e:
        print(f"✗ Failed to connect to SQLite: {e}")
        sys.exit(1)

    try:
        with postgres_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✓ PostgreSQL connection successful")
    except Exception as e:
        print(f"✗ Failed to connect to PostgreSQL: {e}")
        sys.exit(1)

    print()

    # Migrate tables in order
    total_rows = 0
    for table_name in get_table_order():
        rows = migrate_table(sqlite_engine, postgres_engine, table_name)
        total_rows += rows

    # Reset sequences
    reset_sequences(postgres_engine)

    # Verify migration
    if not args.skip_verification:
        if verify_migration(sqlite_engine, postgres_engine):
            print("\n✓ Migration completed successfully!")
            print(f"  Total rows migrated: {total_rows}")
        else:
            print("\n✗ Migration verification failed! Please check the differences above.")
            sys.exit(1)
    else:
        print(f"\n✓ Migration completed! (verification skipped)")
        print(f"  Total rows migrated: {total_rows}")


if __name__ == "__main__":
    main()
