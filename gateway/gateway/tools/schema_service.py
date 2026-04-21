"""Pure helpers for schema tool payload and text rendering."""

from __future__ import annotations

from gateway.tools._row_helpers import row_as_dict, row_get, row_has_key


def render_schemas(rows: list) -> str:
    lines = [f"  {r['schema_name']} ({r['tables']} tables)" for r in rows]
    return "Schemas:\n" + "\n".join(lines) if lines else "No user schemas found"


def render_tables(schema: str, rows: list) -> str:
    if not rows:
        return f"No tables in schema '{schema}'"
    lines = [f"  {r['name']} ({r['type']}) — ~{r['approx_rows']} rows, {r['total_size']}" for r in rows]
    return f"Tables in '{schema}':\n" + "\n".join(lines)


def build_table_info_payload(cols: list, pk_rows: list, fk_rows: list, idx_rows: list, stats_row) -> dict:
    payload = {
        "columns": [row_as_dict(c) for c in cols],
        "primary_key": [r["attname"] for r in pk_rows],
        "foreign_keys": [row_as_dict(r) for r in fk_rows],
        "indexes": [row_as_dict(r) for r in idx_rows],
    }
    if stats_row:
        payload["stats"] = row_as_dict(stats_row)
    return payload


def render_indexes(rows: list, table: str | None) -> str:
    if not rows:
        return "No indexes found"
    lines = []
    for r in rows:
        prefix = f"{row_get(r, 'tablename', table)}." if row_has_key(r, "tablename") else ""
        scans = row_get(r, "idx_scan", 0)
        lines.append(f"  {prefix}{r['indexname']} ({r['size']}, {scans} scans)\n    {r['indexdef']}")
    return "\n".join(lines)


def render_functions(schema: str, rows: list) -> str:
    if not rows:
        return f"No functions in schema '{schema}'"
    lines = [f"  {r['name']}({r['arguments']}) -> {r['return_type']} [{r['kind']}]" for r in rows]
    return f"Functions in '{schema}':\n" + "\n".join(lines)
