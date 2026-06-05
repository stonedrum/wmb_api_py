from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Iterator

import pymysql
from pymysql.cursors import DictCursor

from .config import settings


@contextmanager
def connection() -> Iterator[pymysql.connections.Connection]:
    conn = pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
        charset=settings.db_charset,
        connect_timeout=settings.db_connect_timeout,
        cursorclass=DictCursor,
        autocommit=False,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_one(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()


def fetch_all(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())


def execute(sql: str, params: tuple[Any, ...] = ()) -> int:
    with connection() as conn:
        with conn.cursor() as cur:
            return cur.execute(sql, params)


@lru_cache(maxsize=64)
def table_columns(table: str) -> set[str]:
    rows = fetch_all(f"SHOW COLUMNS FROM `{table}`")
    return {str(row["Field"]) for row in rows}


def table_exists(table: str) -> bool:
    try:
        table_columns(table)
        return True
    except Exception:
        return False
