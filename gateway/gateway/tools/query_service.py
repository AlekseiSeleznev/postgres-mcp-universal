"""Pure helpers for SQL query tool behavior and response formatting."""

from __future__ import annotations

import json
import re


def strip_leading_comments(sql: str) -> str:
    """Remove leading SQL comments for safer statement classification."""
    stripped = sql.strip().lower()
    while stripped.startswith("--"):
        stripped = stripped.split("\n", 1)[-1].strip().lower()
    while stripped.startswith("/*"):
        idx = stripped.find("*/")
        if idx < 0:
            break
        stripped = stripped[idx + 2 :].strip().lower()
    return stripped


def is_read_only_sql(sql: str, read_only_prefixes: tuple[str, ...], write_keywords: set[str]) -> bool:
    """Detect whether SQL is safe for restricted (read-only) execution mode."""
    stripped = strip_leading_comments(sql)
    if not stripped.startswith(read_only_prefixes):
        return False
    if stripped.startswith("with"):
        no_strings = re.sub(r"'[^']*'", "", stripped)
        words = set(re.findall(r"\b[a-z]+\b", no_strings))
        if words & write_keywords:
            return False
    return True


def format_table_text(columns: list[str], rows: list[tuple]) -> str:
    """Render rows into an aligned fixed-width text table."""
    if not rows:
        return f"Columns: {', '.join(columns)}\n(0 rows)"

    str_rows = [[str(v) for v in row] for row in rows]
    widths = [max(len(c), *(len(r[i]) for r in str_rows)) for i, c in enumerate(columns)]

    header = " | ".join(c.ljust(w) for c, w in zip(columns, widths))
    separator = "-+-".join("-" * w for w in widths)

    lines = [header, separator]
    for row in str_rows:
        lines.append(" | ".join(v.ljust(w) for v, w in zip(row, widths)))
    lines.append(f"({len(rows)} row{'s' if len(rows) != 1 else ''})")
    return "\n".join(lines)


def format_query_result_text(records: list, elapsed_s: float, max_rows: int) -> str:
    """Render execute_sql output text with truncation metadata."""
    if not records:
        return f"Query executed successfully ({elapsed_s:.3f}s)\n(0 rows)"

    columns = list(records[0].keys())
    truncated = len(records) > max_rows
    rows = [tuple(r.values()) for r in records[:max_rows]]
    table = format_table_text(columns, rows)

    suffix = ""
    if truncated:
        suffix = f"\n... truncated to {max_rows} rows (total: {len(records)})"
    return f"{table}{suffix}\nTime: {elapsed_s:.3f}s"


def parse_explain_plan(raw_plan):
    """Parse JSON plan payload from asyncpg record cell if possible."""
    if isinstance(raw_plan, str):
        try:
            return json.loads(raw_plan)
        except json.JSONDecodeError:
            return raw_plan
    return raw_plan
