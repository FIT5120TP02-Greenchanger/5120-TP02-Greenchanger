"""Tests for the CI guard that protects already-applied migrations.

The guard itself lives at .github/scripts/check_migrations.py and runs in the
data-tests job. It is tested from the backend suite because that is the only
job with pytest available.

Each test builds a throwaway git repository so the assertions do not depend on
this repository's own history.
"""
# pyproject: pytest 


import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "check_migrations.py"
MIGRATIONS = "migrations/"

# The guard is designed to block any changes to already-applied migrations in the
# GreenChanger_data/greenchanger_sql/migrations/ directory. It does this by
# running a git diff command that filters out any added files and checks for any
def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

# if any other changes are present. The tests below create a temporary git
# repository, add some migrations, and then attempt to modify, delete, or rename
# them. The guard should fail in all these cases, and pass when a new migration
# is added or when changes are made outside the migrations directory.
def run_guard(repo):
    """Run the guard against main...feature and return its exit code."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "main", "feature", MIGRATIONS],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout


@pytest.fixture
def repo(tmp_path):
    """A repo with two applied migrations on main and a feature branch checked out."""
    git(tmp_path, "init", "-q", ".")
    git(tmp_path, "config", "user.email", "ci@example.com")
    git(tmp_path, "config", "user.name", "ci")

    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "001_schema.sql").write_text("SELECT 1;\n")
    (tmp_path / "migrations" / "002_seed.sql").write_text("SELECT 2;\n")

    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "applied migrations")
    git(tmp_path, "branch", "-M", "main")
    git(tmp_path, "checkout", "-qb", "feature")
    return tmp_path


def test_renaming_an_applied_migration_fails(repo):
    """The case the original grep-based guard let through."""
    git(repo, "mv", "migrations/001_schema.sql", "migrations/001_renamed.sql")
    git(repo, "commit", "-qm", "rename")

    code, output = run_guard(repo)

    assert code == 1
    assert "001_schema.sql" in output

# test cases for modifying, deleting, and adding migrations
def test_modifying_an_applied_migration_fails(repo):
    (repo / "migrations" / "001_schema.sql").write_text("SELECT 999;\n")
    git(repo, "commit", "-qam", "modify")

    code, output = run_guard(repo)

    assert code == 1
    assert "001_schema.sql" in output

# test deleting an applied migration fails
def test_deleting_an_applied_migration_fails(repo):
    git(repo, "rm", "-q", "migrations/001_schema.sql")
    git(repo, "commit", "-qm", "delete")

    code, output = run_guard(repo)

    assert code == 1
    assert "001_schema.sql" in output


def test_adding_a_new_migration_passes(repo):
    (repo / "migrations" / "003_new.sql").write_text("SELECT 3;\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "add")

    code, _ = run_guard(repo)

    assert code == 0


def test_changes_outside_migrations_are_ignored(repo):
    (repo / "README.md").write_text("unrelated\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "docs")

    code, _ = run_guard(repo)

    assert code == 0
