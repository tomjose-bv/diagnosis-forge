"""Read-only SQL for agents and evidence checks: one SELECT/WITH statement, no file or settings
access, a time limit and a row limit.

This is a safety measure for a local demo, not a security boundary.
"""

from __future__ import annotations

import re
import threading
from typing import Any

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|create|drop|alter|attach|detach|copy|pragma|install|load|export|import|call|set|"
    r"reset|checkpoint|vacuum|truncate|grant|revoke|begin|commit|rollback|use)\b"
    r"|\b(read_\w+|glob|sniff_csv|parquet_\w+|query_table|getenv)\s*\(",
    re.IGNORECASE,
)


class SQLError(ValueError):
    pass


def _strip(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return sql.strip().rstrip(";").strip()


def check(sql: str) -> str:
    """Return the cleaned statement or raise SQLError explaining why it is not allowed."""
    if not isinstance(sql, str) or not sql.strip():
        raise SQLError("empty query")
    body = _strip(sql)
    no_strings = re.sub(r"'(?:[^']|'')*'", "''", body)
    if ";" in no_strings:
        raise SQLError("only one statement is allowed")
    if not re.match(r"^(select|with)\b", body, re.IGNORECASE):
        raise SQLError("only SELECT or WITH queries are allowed")
    m = FORBIDDEN.search(no_strings)
    if m:
        raise SQLError(f"not allowed in queries: {m.group(0).strip()}")
    return body


def run(con, sql: str, max_rows: int = 200, timeout: float = 10.0) -> tuple[list[str], list[tuple[Any, ...]], bool]:
    """Run a checked query. Returns (column names, rows, truncated)."""
    body = check(sql)
    timer = threading.Timer(timeout, con.interrupt)
    timer.start()
    try:
        cur = con.execute(body)
        rows = cur.fetchmany(max_rows + 1)
        cols = [d[0] for d in cur.description or []]
    except Exception as e:  # duckdb errors, interrupts
        msg = str(e).splitlines()[0][:300]
        raise SQLError(f"query failed: {msg}") from None
    finally:
        timer.cancel()
    return cols, rows[:max_rows], len(rows) > max_rows
