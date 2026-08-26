"""Apply the GreenChanger schema and idempotent reference-data seeds."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_script import db  # noqa: E402


def execute_file(connection, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    with connection.cursor() as cursor:
        cursor.execute(sql)
    print(f"Applied: {path.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Create tables and indexes without inserting reference data.",
    )
    parser.add_argument(
        "--confirm-shared",
        action="store_true",
        help="Required before changing the team's shared Aurora database.",
    )
    args = parser.parse_args()

    if not db.is_local() and not args.confirm_shared:
        raise SystemExit(
            "Refusing to change the shared database without --confirm-shared.\n"
            "Use a local DB_HOST for development, or review the SQL and explicitly "
            "confirm the shared target."
        )

    connection = db.connect()
    try:
        execute_file(connection, ROOT / "greenchanger_sql" / "schema.sql")
        if not args.schema_only:
            execute_file(
                connection,
                ROOT / "greenchanger_sql" / "seeds" / "001_reference_data.sql",
            )
            execute_file(
                connection,
                ROOT / "greenchanger_sql" / "analytics" / "001_views.sql",
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
