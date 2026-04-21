"""Tests for gateway.tools.schema_service pure helpers."""

from __future__ import annotations
from gateway.tools.schema_service import (
    build_table_info_payload,
    render_functions,
    render_indexes,
    render_schemas,
    render_tables,
    row_as_dict,
    row_get,
    row_has_key,
)


def _rec(data: dict):
    class _Rec:
        def __getitem__(self, k):
            return data[k]

        def keys(self):
            return list(data.keys())

        def get(self, k, default=None):
            return data.get(k, default)

        def items(self):
            return data.items()

    return _Rec()


def test_render_schemas_and_tables():
    schemas = [_rec({"schema_name": "public", "tables": 5})]
    assert "public (5 tables)" in render_schemas(schemas)
    tables = [_rec({"name": "users", "type": "table", "approx_rows": 10, "total_size": "16 kB"})]
    assert "users (table)" in render_tables("public", tables)


def test_build_table_info_payload_with_stats():
    payload = build_table_info_payload(
        cols=[_rec({"column_name": "id"})],
        pk_rows=[_rec({"attname": "id"})],
        fk_rows=[],
        idx_rows=[_rec({"indexname": "users_pkey"})],
        stats_row=_rec({"approx_rows": 123}),
    )
    assert payload["primary_key"] == ["id"]
    assert payload["stats"]["approx_rows"] == 123


def test_render_indexes_and_functions():
    indexes = [
        _rec(
            {
                "tablename": "users",
                "indexname": "users_pkey",
                "indexdef": "CREATE INDEX users_pkey ...",
                "size": "8 kB",
                "idx_scan": 11,
            }
        )
    ]
    rendered_idx = render_indexes(indexes, table=None)
    assert "users.users_pkey" in rendered_idx
    assert "11 scans" in rendered_idx

    funcs = [_rec({"name": "f", "arguments": "", "return_type": "int4", "kind": "function"})]
    rendered_fn = render_functions("public", funcs)
    assert "Functions in 'public'" in rendered_fn
    assert "f() -> int4 [function]" in rendered_fn


def test_schema_row_helpers_and_empty_rendering():
    class KeysOnly:
        def keys(self):
            return ["name"]

        def __getitem__(self, key):
            if key == "name":
                return "users"
            raise KeyError(key)

    class ContainerOnly:
        def __contains__(self, key):
            return key == "tablename"

    class Broken:
        pass

    assert row_as_dict({"a": 1}) == {"a": 1}
    assert row_as_dict(KeysOnly()) == {"name": "users"}
    assert row_as_dict(Broken()) == {}
    assert row_get({"a": 1}, "a") == 1
    assert row_get(Broken(), "a", "fallback") == "fallback"
    assert row_has_key({"tablename": "users"}, "tablename") is True
    assert row_has_key(ContainerOnly(), "tablename") is True
    assert row_has_key(Broken(), "tablename") is False
    assert render_schemas([]) == "No user schemas found"
    assert render_tables("public", []) == "No tables in schema 'public'"
    assert render_indexes([], table="users") == "No indexes found"
    assert render_functions("public", []) == "No functions in schema 'public'"


def test_row_as_dict_fallbacks_cover_keys_and_items_paths():
    class KeysFallback:
        def keys(self):
            return ["name"]

        def __getitem__(self, key):
            return "users"

    class ItemsFallback:
        def items(self):
            return [("state", "ok")]

    assert row_as_dict(KeysFallback()) == {"name": "users"}
    assert row_as_dict(ItemsFallback()) == {"state": "ok"}


def test_row_has_key_tolerates_broken_keys_and_build_payload_without_stats():
    class BrokenKeys:
        def keys(self):
            raise RuntimeError("boom")

        def __contains__(self, key):
            return key == "tablename"

    assert row_has_key(BrokenKeys(), "tablename") is True

    payload = build_table_info_payload(
        cols=[_rec({"column_name": "id"})],
        pk_rows=[],
        fk_rows=[],
        idx_rows=[],
        stats_row=None,
    )
    assert "stats" not in payload


def test_row_as_dict_handles_broken_keys_and_items_gracefully():
    class BrokenEverywhere:
        def keys(self):
            raise RuntimeError("boom")

        def items(self):
            raise RuntimeError("boom")

        def __iter__(self):
            raise RuntimeError("boom")

    assert row_as_dict(BrokenEverywhere()) == {}
