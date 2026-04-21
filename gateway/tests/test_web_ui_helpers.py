"""Tests for gateway.web_ui_helpers utility functions."""

from __future__ import annotations

from gateway.web_ui_helpers import (
    error_response,
    json_response,
    merge_password_from_old_uri,
    safe_uri_for_dashboard,
)


def test_json_and_error_response_helpers():
    ok = json_response({"ok": True}, status_code=201)
    assert ok.status_code == 201
    assert ok.media_type == "application/json"
    assert b'"ok": true' in ok.body

    err = error_response("boom", status_code=418)
    assert err.status_code == 418
    assert b'"error": "boom"' in err.body


def test_safe_uri_for_dashboard_prefers_safe_uri_and_falls_back_to_raw_uri():
    class Safe:
        uri = "postgresql://raw"

        def safe_uri(self):
            return "postgresql://safe"

    class EmptySafe:
        uri = "postgresql://raw"

        def safe_uri(self):
            return ""

    class BrokenSafe:
        uri = "postgresql://raw"

        def safe_uri(self):
            raise RuntimeError("broken")

    class NonStringSafe:
        uri = "postgresql://raw"

        def safe_uri(self):
            return 123

    class NoSafeUri:
        uri = "postgresql://raw"

    assert safe_uri_for_dashboard(Safe()) == "postgresql://safe"
    assert safe_uri_for_dashboard(EmptySafe()) == "postgresql://raw"
    assert safe_uri_for_dashboard(BrokenSafe()) == "postgresql://raw"
    assert safe_uri_for_dashboard(NonStringSafe()) == "postgresql://raw"
    assert safe_uri_for_dashboard(NoSafeUri()) == "postgresql://raw"


def test_merge_password_from_old_uri_preserves_compatible_secret():
    merged = merge_password_from_old_uri(
        "postgresql://user@[2001:db8::1]:5432/dbname",
        "postgresql://user:old%20secret@[2001:db8::1]:5432/dbname",
    )
    assert "old%20secret" in merged
    assert "@[2001:db8::1]:5432" in merged


def test_merge_password_from_old_uri_rejects_incompatible_changes():
    with_password = merge_password_from_old_uri(
        "postgresql://user:new@localhost/db",
        "postgresql://user:old@localhost/db",
    )
    assert with_password == "postgresql://user:new@localhost/db"

    different_user = merge_password_from_old_uri(
        "postgresql://other@localhost/db",
        "postgresql://user:old@localhost/db",
    )
    assert different_user == "postgresql://other@localhost/db"

    different_host = merge_password_from_old_uri(
        "postgresql://user@db2.local/db",
        "postgresql://user:old@db1.local/db",
    )
    assert different_host == "postgresql://user@db2.local/db"

    no_user = merge_password_from_old_uri(
        "postgresql://db1.local/db",
        "postgresql://user:old@db1.local/db",
    )
    assert no_user == "postgresql://db1.local/db"
