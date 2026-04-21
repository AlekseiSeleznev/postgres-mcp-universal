"""Tests for gateway.tools.query_service pure helper functions."""

from __future__ import annotations

from gateway.tools.query_service import (
    format_query_result_text,
    format_table_text,
    is_read_only_sql,
    strip_leading_comments,
    parse_explain_plan,
)


READ_ONLY_PREFIXES = ("select", "explain", "show", "with", "values", "table")
WRITE_KEYWORDS = {"insert", "update", "delete", "merge", "truncate", "drop", "alter", "create", "grant", "revoke"}


class _Rec:
    def __init__(self, data: dict):
        self._data = data

    def keys(self):
        return list(self._data.keys())

    def values(self):
        return list(self._data.values())


def test_is_read_only_sql_detects_writable_cte():
    sql = "WITH d AS (DELETE FROM t RETURNING id) SELECT * FROM d"
    assert is_read_only_sql(sql, READ_ONLY_PREFIXES, WRITE_KEYWORDS) is False


def test_is_read_only_sql_allows_select_with_quoted_write_words():
    sql = "WITH x AS (SELECT 'delete me' AS note) SELECT * FROM x"
    assert is_read_only_sql(sql, READ_ONLY_PREFIXES, WRITE_KEYWORDS) is True


def test_format_table_text_and_query_result():
    rows = [_Rec({"id": 1, "name": "alice"}), _Rec({"id": 2, "name": "bob"})]
    table = format_table_text(["id", "name"], [(1, "alice"), (2, "bob")])
    assert "alice" in table
    rendered = format_query_result_text(rows, elapsed_s=0.123, max_rows=1)
    assert "truncated to 1 rows" in rendered
    assert "Time: 0.123s" in rendered


def test_parse_explain_plan_handles_json_and_raw_text():
    parsed = parse_explain_plan('[{"Plan":{"Node Type":"Seq Scan"}}]')
    assert isinstance(parsed, list)
    raw = parse_explain_plan("not json")
    assert raw == "not json"


def test_strip_leading_comments_handles_dash_and_unclosed_block_comment():
    assert strip_leading_comments("-- note\nSELECT 1") == "select 1"
    assert strip_leading_comments("/* broken comment\nSELECT 1") == "/* broken comment\nselect 1"


def test_parse_explain_plan_returns_non_string_payload_as_is():
    payload = [{"Plan": {"Node Type": "Index Scan"}}]
    assert parse_explain_plan(payload) is payload
