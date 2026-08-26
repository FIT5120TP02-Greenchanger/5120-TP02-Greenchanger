"""Apply numbered GreenChanger PostgreSQL migrations in order."""

from __future__ import annotations

import argparse
from hashlib import sha256
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_script import db  # noqa: E402


MIGRATIONS = ROOT / "greenchanger_sql" / "migrations"
MIGRATION_NAME = re.compile(r"^(\d+)_.*\.sql$")
INCLUDE_LINE = re.compile(r"^\s*--\s*include:\s*(.+?)\s*$", re.MULTILINE)


def ensure_version_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            filename TEXT NOT NULL,
            checksum CHAR(64) NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def applied_versions(cursor) -> dict[int, dict]:
    """Return migrations already recorded by this database."""

    ensure_version_table(cursor)
    cursor.execute(
        "SELECT version, filename, checksum, applied_at FROM schema_version"
    )
    return {row["version"]: row for row in cursor.fetchall()}


def migration_files() -> list[tuple[int, pathlib.Path]]:
    """Return every numbered migration on disk, oldest first."""

    found: list[tuple[int, pathlib.Path]] = []
    versions: set[int] = set()
    for path in sorted(MIGRATIONS.glob("*.sql")):
        match = MIGRATION_NAME.match(path.name)
        if not match:
            raise ValueError(f"Invalid migration filename: {path.name}")
        version = int(match.group(1))
        if version in versions:
            raise ValueError(f"Duplicate migration version: {version}")
        versions.add(version)
        found.append((version, path))
    return sorted(found, key=lambda item: item[0])


def expanded_sql(path: pathlib.Path, seen: set[pathlib.Path] | None = None) -> str:
    """Expand `-- include: relative/path.sql` directives recursively."""

    resolved = path.resolve()
    active = set() if seen is None else set(seen)
    if resolved in active:
        raise ValueError(f"Circular SQL include detected at {path}")
    active.add(resolved)
    text = path.read_text(encoding="utf-8")

    def replace_include(match: re.Match[str]) -> str:
        include_path = (path.parent / match.group(1).strip()).resolve()
        if not include_path.is_file():
            raise FileNotFoundError(f"SQL include does not exist: {include_path}")
        return expanded_sql(include_path, active)

    return INCLUDE_LINE.sub(replace_include, text)


def migration_checksum(path: pathlib.Path) -> str:
    return sha256(expanded_sql(path).encode("utf-8")).hexdigest()


def executable_sql(path: pathlib.Path) -> str:
    """Remove transaction commands because the runner owns the transaction."""

    text = expanded_sql(path)
    text = re.sub(r"^\s*BEGIN\s*;\s*$", "", text, flags=re.I | re.M)
    text = re.sub(r"^\s*COMMIT\s*;\s*$", "", text, flags=re.I | re.M)
    return text.strip()


def check_applied_files(done: dict[int, dict], files: list[tuple[int, pathlib.Path]]) -> None:
    """Reject missing or changed migrations that were already recorded."""

    paths = dict(files)
    for version, record in done.items():
        path = paths.get(version)
        if path is None:
            raise RuntimeError(
                f"Applied migration {version} ({record['filename']}) is missing"
            )
        if record["checksum"] != migration_checksum(path):
            raise RuntimeError(
                f"Applied migration changed: {path.name}. "
                "Create a new numbered migration instead."
            )


def status(connection) -> None:
    with connection.cursor() as cursor:
        done = applied_versions(cursor)
        available = migration_files()
        check_applied_files(done, available)
        for version, path in available:
            state = "applied" if version in done else "PENDING"
            print(f"  {state:<7}  {path.name}")
    connection.rollback()


def migrate(connection, *, baseline: bool = False) -> None:
    """Apply or baseline pending migrations as one transaction."""

    with connection.cursor() as cursor:
        done = applied_versions(cursor)
        available = migration_files()
        check_applied_files(done, available)
        pending = [(v, p) for v, p in available if v not in done]
        if not pending:
            print("nothing to do; the database is up to date")
            connection.commit()
            return

        try:
            for version, path in pending:
                checksum = migration_checksum(path)
                if baseline:
                    print(f"marked  {path.name}  (not executed)")
                else:
                    sql_text = executable_sql(path)
                    if sql_text:
                        cursor.execute(sql_text)
                    print(f"applied {path.name}")
                cursor.execute(
                    """INSERT INTO schema_version (version, filename, checksum)
                       VALUES (%s, %s, %s)""",
                    (version, path.name, checksum),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def reset(connection) -> None:
    """Drop application tables. Local sandbox only."""

    if not db.is_local():
        sys.exit(
            f"refusing to --reset {db.host()}\n"
            "That is the shared database. Point DB_HOST at a local sandbox."
        )

    from psycopg import sql

    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT schemaname, tablename FROM pg_tables
               WHERE schemaname = 'public' ORDER BY tablename"""
        )
        tables = cursor.fetchall()
        if not tables:
            print("nothing to drop")
            connection.rollback()
            return
        for row in tables:
            cursor.execute(
                sql.SQL("DROP TABLE {}.{} CASCADE").format(
                    sql.Identifier(row["schemaname"]),
                    sql.Identifier(row["tablename"]),
                )
            )
            print("dropped", row["tablename"])
    connection.commit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--status", action="store_true")
    action.add_argument("--baseline", action="store_true")
    action.add_argument("--reset", action="store_true")
    parser.add_argument(
        "--confirm-shared",
        action="store_true",
        help="Required before migrating or baselining shared Aurora.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.reset and not db.is_local():
        sys.exit(
            f"refusing to --reset {db.host()}\n"
            "That is the shared database. Point DB_HOST at a local sandbox."
        )
    if not args.status and not args.reset and not db.is_local() and not args.confirm_shared:
        sys.exit(
            "Refusing to modify the shared database without --confirm-shared.\n"
            "Use --status to inspect it, or explicitly confirm the shared target."
        )

    connection = db.connect()
    try:
        if args.status:
            status(connection)
        elif args.reset:
            reset(connection)
        else:
            migrate(connection, baseline=args.baseline)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
