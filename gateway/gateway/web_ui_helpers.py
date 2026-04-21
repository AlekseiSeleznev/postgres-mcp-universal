"""Shared helpers for PostgreSQL dashboard API handlers."""

from __future__ import annotations

import json
import re
from urllib.parse import quote, unquote, urlparse, urlunparse

from starlette.responses import Response

from gateway.web_ui_content import DASHBOARD_HTML, _T

# Database name: letters, digits, hyphens, underscores only
DB_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$")


def json_response(data, status_code: int = 200) -> Response:
    body = json.dumps(data, ensure_ascii=False, default=str)
    return Response(body, status_code=status_code, media_type="application/json")


def error_response(message: str, status_code: int = 400) -> Response:
    return json_response({"error": str(message)}, status_code=status_code)


def render_dashboard(lang: str = "ru") -> str:
    t = _T.get(lang, _T["ru"])
    html = DASHBOARD_HTML
    for k, v in t.items():
        html = html.replace("{{" + k + "}}", v)
    html = html.replace("{{lang}}", lang)
    html = html.replace("{{ru_on}}", "on" if lang == "ru" else "")
    html = html.replace("{{en_on}}", "on" if lang == "en" else "")
    html = html.replace("{{t_json}}", json.dumps(t, ensure_ascii=False))
    return html


def safe_uri_for_dashboard(db) -> str:
    safe_uri_fn = getattr(db, "safe_uri", None)
    if callable(safe_uri_fn):
        try:
            safe = safe_uri_fn()
            if isinstance(safe, str) and safe:
                return safe
        except Exception:
            pass
    return str(getattr(db, "uri", ""))


def merge_password_from_old_uri(new_uri: str, old_uri: str) -> str:
    """Keep password from old URI when edited URI omits it."""
    try:
        new_p = urlparse(new_uri)
        old_p = urlparse(old_uri)
        if new_p.password is not None:
            return new_uri
        if not old_p.password or not new_p.username:
            return new_uri
        if old_p.username and old_p.username != new_p.username:
            return new_uri
        if old_p.hostname and new_p.hostname and old_p.hostname != new_p.hostname:
            return new_uri

        host = new_p.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        user = quote(new_p.username, safe="")
        password = quote(unquote(old_p.password), safe="")
        netloc = f"{user}:{password}@{host}"
        if new_p.port:
            netloc += f":{new_p.port}"
        return urlunparse(new_p._replace(netloc=netloc))
    except Exception:
        return new_uri
