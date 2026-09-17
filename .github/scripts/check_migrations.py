#!/usr/bin/env python3
"""Reject any change to an already-applied migration.

Migrations under GreenChanger_data/greenchanger_sql/migrations/ are
forward-only and are already applied to the shared Aurora cluster. A pull
request may only ADD a new numbered file. Modifying, deleting, renaming or
copying an existing one silently desynchronises the shared database from the
repository, so every status other than "A" fails the build.

Usage:
    python .github/scripts/check_migrations.py <base> <head> [path]
"""

import subprocess
import sys

DEFAULT_PATH = "GreenChanger_data/greenchanger_sql/migrations/"


def offending_changes(base, head, path=DEFAULT_PATH, repo=None):
    """Return `git diff --name-status` lines for non-added changes under path.

    `--diff-filter=a` is the lowercase (exclude) form: it selects every status
    except A. Listing statuses positively is what let renames through before -
    git reports those as R<score>, not a bare R.
    """
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-status",
            "--diff-filter=a",
            f"{base}...{head}",
            "--",
            path,
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=repo,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def main(argv):
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2

    base, head = argv[1], argv[2]
    path = argv[3] if len(argv) > 3 else DEFAULT_PATH

    offenders = offending_changes(base, head, path)
    if not offenders:
        return 0

    print(
        f"::error::Migrations under {path} are already applied to the shared "
        "Aurora RDS. Add a new numbered file instead of changing, "
        "deleting or renaming an existing one."
    )
    for line in offenders:
        print(line)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
