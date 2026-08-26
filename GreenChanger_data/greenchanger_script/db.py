"""Database connection: the one file that knows where the database is.

Usage:

    import db

    conn = db.connect()

Everything defaults to the team's shared Aurora PostgreSQL instance. The
shared instance uses AWS IAM authentication, so teammates need valid AWS
credentials rather than a stored database password.

Point somewhere else by setting environment variables:

PowerShell:
    $env:DB_HOST="127.0.0.1"
    $env:DB_PORT="5432"
    $env:DB_USER="postgres"
    $env:DB_NAME="greenshift"
    $env:DB_PASSWORD="your-local-password"

bash:
    export DB_HOST=127.0.0.1 DB_PORT=5432 DB_USER=postgres
    export DB_NAME=greenshift DB_PASSWORD=your-local-password
"""

import os
import sys

SHARED_HOST = (
    "greenshift-dev.cluster-cl6ugmisezq2.ap-southeast-2.rds.amazonaws.com"
)
SHARED_PORT = 5432
SHARED_USER = "greenshift_admin"
SHARED_NAME = "postgres"
SHARED_REGION = "ap-southeast-2"


def host():
    """Return the configured database host."""

    return os.environ.get("DB_HOST", SHARED_HOST)


def is_local():
    """True when pointed at a local sandbox instead of the shared database.

    Anything destructive should check this first. Rebuilding a local database
    is recoverable; wiping the shared database blocks the whole team.
    """

    return host() in ("127.0.0.1", "localhost", "::1")


def _iam_token():
    """Generate the temporary password token for the shared RDS instance."""

    try:
        import boto3
    except ImportError as error:
        raise RuntimeError(
            "boto3 is required for shared RDS IAM authentication. "
            "Run: python -m pip install -r requirements.txt"
        ) from error

    region = os.environ.get("AWS_REGION", SHARED_REGION)
    port = int(os.environ.get("DB_PORT", SHARED_PORT))
    user = os.environ.get("DB_USER", SHARED_USER)

    return boto3.client("rds", region_name=region).generate_db_auth_token(
        DBHostname=host(),
        Port=port,
        DBUsername=user,
        Region=region,
    )


def _password():
    """Use a local password or generate an IAM token for shared Aurora."""

    password = os.environ.get("DB_PASSWORD")
    if password:
        return password

    if is_local():
        sys.exit(
            "DB_PASSWORD is not set for the local database.\n"
            "  PowerShell:  $env:DB_PASSWORD = Read-Host 'Password'\n"
            "  bash:        read -rs DB_PASSWORD && export DB_PASSWORD\n"
            "The password is deliberately not stored in the repository."
        )

    return _iam_token()


def connect():
    """Open a PostgreSQL connection. The caller is responsible for closing it."""

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as error:
        raise RuntimeError(
            "psycopg is required for database access. "
            "Run: python -m pip install -r requirements.txt"
        ) from error

    return psycopg.connect(
        host=host(),
        port=int(os.environ.get("DB_PORT", SHARED_PORT)),
        user=os.environ.get("DB_USER", SHARED_USER),
        password=_password(),
        dbname=os.environ.get("DB_NAME", SHARED_NAME),
        sslmode=os.environ.get(
            "DB_SSLMODE",
            "disable" if is_local() else "require",
        ),
        connect_timeout=int(os.environ.get("DB_CONNECT_TIMEOUT", "15")),
        application_name="greenshift-data",
        row_factory=dict_row,
    )
