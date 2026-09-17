"""Database access. IAM-authenticated connection pool to the shared Aurora cluster."""

from __future__ import annotations

import os
from collections.abc import Iterator
from decimal import Decimal

import boto3
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

HOST = os.environ.get(
    "DB_HOST", "greenshift-dev.cluster-cl6ugmisezq2.ap-southeast-2.rds.amazonaws.com"
)
PORT = int(os.environ.get("DB_PORT", "5432"))
USER = os.environ.get("DB_USER", "greenshift_api")
NAME = os.environ.get("DB_NAME", "postgres")
REGION = os.environ.get("AWS_REGION", "ap-southeast-2")
SSLMODE = os.environ.get("DB_SSLMODE", "require")


def _iam_token() -> str:
    """Mint a fresh 15-minute IAM auth token. Call once per NEW connection, never cache it."""
    return boto3.client("rds", region_name=REGION).generate_db_auth_token(
        DBHostname=HOST, Port=PORT, DBUsername=USER, Region=REGION
    )


class _IamConnection(psycopg.Connection):
    """A Connection that fetches a fresh IAM token at connect time.

    ConnectionPool stores `kwargs` once at construction and replays it for
    every new physical connection -- it will NOT call a function passed as
    `password`. Overriding connect() here is what makes each new connection
    pick up a *live* token instead of a stale (or never-called) one.
    """

    @classmethod
    def connect(cls, conninfo="", **kwargs):
        kwargs.setdefault("password", _iam_token())
        return super().connect(conninfo, **kwargs)


pool = ConnectionPool(
    conninfo=f"host={HOST} port={PORT} dbname={NAME} user={USER} sslmode={SSLMODE}",
    connection_class=_IamConnection,
    kwargs={"row_factory": dict_row},
    min_size=1,
    max_size=5,
    open=False,
)


def get_db() -> Iterator[psycopg.Connection]:
    """FastAPI dependency: hand out a pooled connection, return it when the request ends."""
    with pool.connection() as conn:
        yield conn

def jsonable_row(row: dict) -> dict:
    """Convert Decimal columns to float so the API always emits JSON numbers."""
    return {
        key: float(value) if isinstance(value, Decimal) else value
        for key, value in row.items()
    }