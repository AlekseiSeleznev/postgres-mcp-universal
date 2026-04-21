"""Service-layer operations for PostgreSQL dashboard API routes."""

from __future__ import annotations

from gateway.web_ui_helpers import DB_NAME_RE, error_response, merge_password_from_old_uri


async def connect_from_request(request, *, registry, pool_manager, database_info_cls):
    body = await request.json()
    name = body.get("name", "").strip()
    uri = body.get("uri", "").strip()
    access_mode = body.get("access_mode", "unrestricted")
    if not name or not uri:
        return error_response("name and uri are required", 400)
    if not DB_NAME_RE.match(name):
        return error_response("Invalid database name. Use only letters, digits, hyphens, underscores (max 63 chars).", 400)

    db = database_info_cls(name=name, uri=uri, access_mode=access_mode)
    registry.add(db)
    try:
        await pool_manager.connect(db)
    except Exception as e:
        registry.remove(name)
        return error_response(str(e), 500)
    return {"ok": True, "name": name}


async def edit_from_request(request, *, registry, pool_manager, database_info_cls):
    """Edit database: disconnect old, connect new, preserve default."""
    body = await request.json()
    old_name = body.get("old_name", "").strip()
    new_name = body.get("name", "").strip()
    uri = body.get("uri", "").strip()
    access_mode = body.get("access_mode", "unrestricted")

    if not old_name or not new_name or not uri:
        return error_response("old_name, name, and uri are required", 400)
    if not DB_NAME_RE.match(new_name):
        return error_response("Invalid database name. Use only letters, digits, hyphens, underscores (max 63 chars).", 400)

    # Remember current default
    was_default = registry.active == old_name
    saved_default = registry.active

    old_db = registry.get(old_name)
    if old_db:
        uri = merge_password_from_old_uri(uri, old_db.uri)

    # Disconnect old
    old_db = registry.remove(old_name)
    if old_db:
        await pool_manager.disconnect(old_name)

    # Connect new
    db = database_info_cls(name=new_name, uri=uri, access_mode=access_mode)
    registry.add(db)
    try:
        await pool_manager.connect(db)
    except Exception as e:
        registry.remove(new_name)
        # Restore old if possible
        if old_db:
            registry.add(old_db)
            try:
                await pool_manager.connect(old_db)
            except Exception:
                pass
        return error_response(str(e), 500)

    # Restore default: if edited db was default, point to new name; otherwise keep old default
    if was_default:
        registry.active = new_name
    elif saved_default and saved_default != old_name:
        registry.active = saved_default
    registry.save()

    return {"ok": True, "name": new_name}
