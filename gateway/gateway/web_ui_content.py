"""Static dashboard templates and docs for PostgreSQL web UI."""

from __future__ import annotations

from gateway import __version__

# ── Translations ────────────────────────────────────────────────────
_T = {
    "ru": {
        "title": "postgres-mcp-universal",
        "subtitle": "MCP-шлюз для PostgreSQL",
        "h_databases": "Базы данных",
        "h_add_db": "Новое подключение",
        "h_edit_db": "Редактирование",
        "conn_name": "Имя соединения",
        "db_name": "Имя базы данных",
        "server": "Сервер",
        "port": "Порт",
        "login": "Логин",
        "password": "Пароль",
        "allow_write": "Разрешить запись",
        "default_db": "По умолчанию",
        "btn_connect": "Подключить",
        "btn_save": "Сохранить",
        "btn_cancel": "Отмена",
        "btn_refresh": "Обновить",
        "btn_edit": "Изменить",
        "btn_delete": "Удалить",
        "btn_docs": "Документация",
        "connected": "Подключена",
        "disconnected": "Отключена",
        "rw": "Чтение/Запись",
        "ro": "Только чтение",
        "no_databases": "Нет подключённых баз данных. Добавьте первую.",
        "confirm_delete": "Удалить соединение",
        "confirm_delete_text": "Вы уверены? Соединение будет разорвано.",
        "fill_fields": "Заполните обязательные поля: имя, сервер, БД, логин",
        "msg_connected": "Подключено",
        "msg_disconnected": "Отключено",
        "msg_saved": "Сохранено",
        "msg_default_set": "Установлено по умолчанию",
        "msg_error": "Ошибка",
        "auth_prompt": "Введите Bearer token для Dashboard API",
    },
    "en": {
        "title": "postgres-mcp-universal",
        "subtitle": "MCP gateway for PostgreSQL",
        "h_databases": "Databases",
        "h_add_db": "New Connection",
        "h_edit_db": "Edit Connection",
        "conn_name": "Connection Name",
        "db_name": "Database Name",
        "server": "Server",
        "port": "Port",
        "login": "Login",
        "password": "Password",
        "allow_write": "Allow writes",
        "default_db": "Default",
        "btn_connect": "Connect",
        "btn_save": "Save",
        "btn_cancel": "Cancel",
        "btn_refresh": "Refresh",
        "btn_edit": "Edit",
        "btn_delete": "Delete",
        "btn_docs": "Docs",
        "connected": "Connected",
        "disconnected": "Disconnected",
        "rw": "Read/Write",
        "ro": "Read-only",
        "no_databases": "No databases connected. Add your first one.",
        "confirm_delete": "Delete connection",
        "confirm_delete_text": "Are you sure? The connection will be closed.",
        "fill_fields": "Fill required fields: name, server, database, login",
        "msg_connected": "Connected",
        "msg_disconnected": "Disconnected",
        "msg_saved": "Saved",
        "msg_default_set": "Set as default",
        "msg_error": "Error",
        "auth_prompt": "Enter Bearer token for Dashboard API",
    },
}

# ── HTML ────────────────────────────────────────────────────────────
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="{{lang}}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>postgres-mcp-universal</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;background:#0f172a;color:#f8fafc;height:100vh;display:flex;flex-direction:column;overflow:hidden}
.content{flex:1;overflow-y:auto}

/* ── Header (1C-style) ── */
.header{background:#1e293b;border-bottom:1px solid #334155;padding:8px 20px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;flex-shrink:0}
.header-left{display:flex;align-items:center;gap:10px}
.header h1{font-size:1.05rem;color:#f8fafc;font-weight:700}
.header .sub{color:#94a3b8;font-size:.75rem}
.header-right{display:flex;align-items:center;gap:6px;flex-wrap:wrap}

/* ── Language switcher (1C-style) ── */
.lang-sw{display:flex;border:1px solid #475569;border-radius:5px;overflow:hidden}
.lang-sw a{padding:3px 8px;font-size:.7rem;color:#94a3b8;display:block;text-decoration:none}
.lang-sw a.on{background:#334155;color:#f8fafc}

/* ── Buttons (1C-style) ── */
.btn{display:inline-flex;align-items:center;gap:4px;padding:5px 12px;border-radius:5px;font-size:.78rem;cursor:pointer;border:1px solid #475569;background:#1e293b;color:#94a3b8;text-decoration:none;transition:.15s}
.btn:hover{background:#334155;color:#f8fafc}
.btn svg{width:13px;height:13px}
.btn-p{background:#0369a1;border-color:#0369a1;color:#fff}
.btn-p:hover{background:#0284c7}
.btn-d{color:#ef4444;border-color:rgba(239,68,68,.25)}
.btn-d:hover{background:rgba(239,68,68,.1);color:#ef4444;border-color:#ef4444}
.btn-ds{background:#991b1b;border-color:#991b1b;color:#fff}
.btn-ds:hover{background:#b91c1c}

/* ── Content ── */
.content{padding:20px}

/* ── Card (1C-style) ── */
.card{background:#1e293b;border-radius:8px;padding:12px;border:1px solid #334155;overflow:hidden;margin-bottom:14px}
.card h2{font-size:.65rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px;font-weight:600}

/* ── DB Item ── */
.db-item{background:#0f172a;border:1px solid #334155;border-radius:6px;padding:10px 12px;margin-bottom:8px;transition:border-color .15s}
.db-item:last-child{margin-bottom:0}
.db-item:hover{border-color:#475569}
.db-row{display:flex;align-items:center;gap:10px}
.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.dot.ok{background:#22c55e}
.dot.err{background:#ef4444}
.db-info{flex:1;min-width:0}
.db-name{font-weight:600;font-size:.88rem}
.db-details{color:#94a3b8;font-size:.75rem;font-family:'SF Mono','Cascadia Code',monospace;margin-top:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.db-badges{display:flex;gap:5px;margin-top:4px;flex-wrap:wrap}
.db-actions{display:flex;gap:4px;flex-shrink:0}

/* ── Badges ── */
.badge{display:inline-flex;align-items:center;padding:1px 6px;border-radius:3px;font-size:.62rem;font-weight:600}
.badge-g{background:rgba(34,197,94,.12);color:#22c55e}
.badge-r{background:rgba(239,68,68,.12);color:#ef4444}
.badge-b{background:rgba(59,130,246,.12);color:#3b82f6}
.badge-c{background:#164e63;color:#22d3ee}

/* ── Default toggle (radio balls) ── */
.rd{display:flex;align-items:center;gap:5px;cursor:pointer;font-size:.72rem;color:#94a3b8;background:none;border:0;padding:0}
.rd:hover{color:#cbd5e1}
.rb{width:14px;height:14px;border-radius:50%;border:2px solid #475569;display:flex;align-items:center;justify-content:center;transition:.15s;flex-shrink:0}
.rb.on{border-color:#22d3ee}
.rb.on::after{content:'';width:7px;height:7px;border-radius:50%;background:#22d3ee}
.rd:hover .rb{border-color:#22d3ee}

/* ── Toggle switch ── */
.toggle{display:flex;align-items:center;gap:8px;cursor:pointer;font-size:.78rem;color:#cbd5e1;user-select:none}
.toggle input{display:none}
.toggle-track{width:34px;height:18px;border-radius:9px;background:#475569;position:relative;transition:.2s;flex-shrink:0}
.toggle-track::after{content:'';width:14px;height:14px;border-radius:50%;background:#94a3b8;position:absolute;top:2px;left:2px;transition:.2s}
.toggle input:checked+.toggle-track{background:#22c55e}
.toggle input:checked+.toggle-track::after{left:18px;background:#fff}

/* ── Form (1C-style) ── */
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.form-group{display:flex;flex-direction:column;gap:3px}
.form-group.full{grid-column:1/-1}
.form-group label{font-size:.65rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.04em;font-weight:600}
input{padding:5px 8px;border-radius:4px;border:1px solid #475569;background:#0f172a;color:#e2e8f0;font-size:.8rem;transition:border .15s;width:100%;-moz-appearance:textfield}
input::-webkit-outer-spin-button,input::-webkit-inner-spin-button{-webkit-appearance:none;margin:0}
input:focus{outline:none;border-color:#38bdf8}
.btn:focus-visible,.lang-sw a:focus-visible,input:focus-visible,.rd:focus-visible{outline:2px solid #38bdf8;outline-offset:2px}
.form-actions{display:flex;gap:6px;justify-content:flex-end;margin-top:10px}

/* ── Empty state ── */
.empty{text-align:center;padding:20px;color:#64748b;font-size:.82rem}

/* ── Overlay (modal) ── */
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:100;display:flex;align-items:center;justify-content:center}
.modal{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:20px;width:480px;max-width:92%}
.modal h3{font-size:.88rem;margin-bottom:14px;color:#f8fafc}
.modal p{color:#cbd5e1}
.modal-actions{display:flex;gap:6px;justify-content:flex-end;margin-top:14px}

/* ── Toast (centered, 1C-style) ── */
.toast-msg{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:#164e63;color:#22d3ee;padding:14px 24px;border-radius:8px;font-size:.9rem;z-index:999;max-width:500px;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,.5);pointer-events:none}
.toast-err{background:#7f1d1d;color:#fca5a5}

/* ── Scrollbar (dark theme) ── */
.content::-webkit-scrollbar{width:8px}
.content::-webkit-scrollbar-track{background:#0f172a}
.content::-webkit-scrollbar-thumb{background:#334155;border-radius:4px}
.content::-webkit-scrollbar-thumb:hover{background:#475569}
.content{scrollbar-width:thin;scrollbar-color:#334155 #0f172a}

/* ── Two-column layout ── */
.cols{display:grid;grid-template-columns:1fr 1fr;gap:14px;align-items:start}

/* ── Footer (1C-style) ── */
.footer{padding:8px 20px;text-align:center;color:#475569;font-size:.68rem;border-top:1px solid #1e293b;flex-shrink:0}
.footer a{color:#64748b;text-decoration:none}.footer a:hover{color:#94a3b8}

@media(max-width:900px){
  .cols{grid-template-columns:1fr}
}
@media(max-width:600px){
  .content{padding:10px}
  .form-grid{grid-template-columns:1fr}
  .db-row{flex-wrap:wrap}
  .db-actions{width:100%;justify-content:flex-end}
}
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <div><h1>postgres-mcp-universal</h1><span class="sub">{{subtitle}}</span></div>
  </div>
  <div class="header-right">
    <div class="lang-sw">
      <a href="?lang=ru" class="{{ru_on}}">RU</a>
      <a href="?lang=en" class="{{en_on}}">EN</a>
    </div>
    <a class="btn" href="/dashboard/docs?lang={{lang}}" target="_blank">{{btn_docs}}</a>
    <button class="btn" onclick="loadDatabases()">{{btn_refresh}}</button>
  </div>
</div>

<div class="content">
<div class="cols">

  <!-- ── Database list ── -->
  <div class="card">
    <h2>{{h_databases}}</h2>
    <div id="db-list" aria-live="polite"></div>
  </div>

  <!-- ── Add database form ── -->
  <div class="card" id="add-card">
    <h2>{{h_add_db}}</h2>
    <div class="form-grid">
      <div class="form-group">
        <label>{{conn_name}} *</label>
        <input id="f-name">
      </div>
      <div class="form-group">
        <label>{{db_name}} *</label>
        <input id="f-db">
      </div>
      <div class="form-group">
        <label>{{server}} *</label>
        <input id="f-host">
      </div>
      <div class="form-group">
        <label>{{port}}</label>
        <input id="f-port" value="5432">
      </div>
      <div class="form-group">
        <label>{{login}} *</label>
        <input id="f-user" value="postgres">
      </div>
      <div class="form-group">
        <label>{{password}}</label>
        <input id="f-pass" type="password">
      </div>
      <div class="form-group full" style="margin-top:2px">
        <label class="toggle">
          <input type="checkbox" id="f-write" checked>
          <span class="toggle-track"></span>
          {{allow_write}}
        </label>
      </div>
    </div>
    <div class="form-actions">
      <button class="btn" onclick="connectDb()">&#8594; {{btn_connect}}</button>
    </div>
  </div>

</div>
</div>

<script>
const T = {{t_json}};
const _API_KEY_STORAGE = 'pg_mcp_dashboard_api_key';
let _API_KEY = sessionStorage.getItem(_API_KEY_STORAGE) || '';

function toast(msg, isErr) {
  var d = document.createElement('div');
  d.className = 'toast-msg' + (isErr ? ' toast-err' : '');
  d.textContent = msg;
  document.body.appendChild(d);
  setTimeout(function(){ d.remove() }, 3000);
}

async function api(url, opts, retryAuth) {
  try {
    opts = opts || {};
    if (typeof retryAuth === 'undefined') retryAuth = true;
    const headers = Object.assign({}, opts.headers || {});
    if (_API_KEY) {
      headers['Authorization'] = 'Bearer ' + _API_KEY;
    }
    const r = await fetch(url, Object.assign({}, opts, { headers: headers }));
    if (r.status === 401) {
      if (retryAuth) {
        const entered = window.prompt(T.auth_prompt || 'Enter Bearer token');
        if (entered && entered.trim()) {
          _API_KEY = entered.trim();
          sessionStorage.setItem(_API_KEY_STORAGE, _API_KEY);
          return api(url, opts, false);
        }
      }
      toast(T.msg_error + ': unauthorized', true);
      return null;
    }
    return await r.json();
  } catch(e) { toast(T.msg_error + ': ' + e.message, true); return null; }
}

/* ═══ XSS PROTECTION ═══ */
function escHtml(s) {
  var d = document.createElement('div');
  d.appendChild(document.createTextNode(s || ''));
  return d.innerHTML;
}
function escAttr(s) {
  return escHtml(s).replace(/'/g, '&#39;').replace(/"/g, '&quot;');
}

function buildUri(host, port, db, user, pass) {
  const p = pass ? encodeURIComponent(pass) : '';
  const auth = p ? user + ':' + p + '@' : user + '@';
  return 'postgresql://' + auth + host + ':' + (port || 5432) + '/' + db;
}

function parseUri(uri) {
  try {
    const m = uri.match(/postgresql:\/\/([^:]+):?([^@]*)@([^:\/]+):?(\d*)\/(.+)/);
    if (m) return { user: m[1], pass: decodeURIComponent(m[2] || ''), host: m[3], port: m[4] || '5432', db: m[5] };
  } catch(e) {}
  return { user: '', pass: '', host: '', port: '5432', db: '' };
}

/* ═══ LOAD DATABASES ═══ */
async function loadDatabases() {
  const [dbs, status] = await Promise.all([api('/api/databases'), api('/api/status')]);
  const list = document.getElementById('db-list');
  const activeDb = status?.active_default || '';

  if (!dbs || dbs.length === 0) {
    list.innerHTML = '<div class="empty">' + T.no_databases + '</div>';
    return;
  }

  list.innerHTML = dbs.map(function(db) {
    const isDefault = db.name === activeDb;
    const dbUri = db.safe_uri || db.uri || '';
    const parts = parseUri(dbUri);
    var eName = escHtml(db.name);
    var eNameAttr = escAttr(db.name);
    return '<div class="db-item">' +
      '<div class="db-row">' +
        '<div class="dot ' + (db.connected ? 'ok' : 'err') + '"></div>' +
        '<div class="db-info">' +
          '<div class="db-name">' + eName + '</div>' +
          '<div class="db-details">' + escHtml(parts.host) + ':' + escHtml(parts.port) + ' / ' + escHtml(parts.db) + ' (' + escHtml(parts.user) + ')</div>' +
          '<div class="db-badges">' +
            '<span class="badge ' + (db.connected ? 'badge-g' : 'badge-r') + '">' +
              (db.connected ? T.connected : T.disconnected) + '</span>' +
            '<span class="badge ' + (db.access_mode === 'unrestricted' ? 'badge-b' : 'badge-c') + '">' +
              (db.access_mode === 'unrestricted' ? T.rw : T.ro) + '</span>' +
          '</div>' +
        '</div>' +
        '<div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px">' +
          '<button type="button" class="rd" aria-pressed="' + (isDefault ? 'true' : 'false') + '" onclick="setDefault(\'' + eNameAttr + '\')">' +
            '<div class="rb ' + (isDefault ? 'on' : '') + '"></div>' +
            '<span>' + T.default_db + '</span>' +
          '</button>' +
          '<div class="db-actions">' +
            '<button class="btn" onclick="editDb(\'' + eNameAttr + '\',\'' + encodeURIComponent(dbUri) + '\',\'' + escAttr(db.access_mode) + '\')">' + T.btn_edit + '</button>' +
            '<button class="btn btn-d" onclick="confirmDelete(\'' + eNameAttr + '\')">' + T.btn_delete + '</button>' +
          '</div>' +
        '</div>' +
      '</div>' +
    '</div>';
  }).join('');
}

/* ═══ CONNECT ═══ */
async function connectDb() {
  const name = document.getElementById('f-name').value.trim();
  const db   = document.getElementById('f-db').value.trim();
  const host = document.getElementById('f-host').value.trim();
  const port = document.getElementById('f-port').value.trim() || '5432';
  const user = document.getElementById('f-user').value.trim();
  const pass = document.getElementById('f-pass').value;
  const write = document.getElementById('f-write').checked;

  if (!name || !host || !db || !user) { toast(T.fill_fields, true); return; }

  const uri = buildUri(host, port, db, user, pass);
  const r = await api('/api/connect', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ name: name, uri: uri, access_mode: write ? 'unrestricted' : 'restricted' })
  });

  if (!r || r.error) { toast(T.msg_error + ': ' + (r?.error || 'unknown'), true); return; }

  toast(T.msg_connected + ': ' + name);
  document.getElementById('f-name').value = '';
  document.getElementById('f-db').value = '';
  document.getElementById('f-host').value = '';
  document.getElementById('f-port').value = '5432';
  document.getElementById('f-user').value = 'postgres';
  document.getElementById('f-pass').value = '';
  document.getElementById('f-write').checked = true;
  loadDatabases();
}

/* ═══ SET DEFAULT ═══ */
async function setDefault(name) {
  const r = await api('/api/switch', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ name: name })
  });
  if (r && r.error) { toast(T.msg_error + ': ' + r.error, true); return; }
  toast(T.msg_default_set + ': ' + name);
  loadDatabases();
}

/* ═══ EDIT (modal) ═══ */
function editDb(name, encodedUri, accessMode) {
  const uri = decodeURIComponent(encodedUri);
  const p = parseUri(uri);

  var ov = document.createElement('div');
  ov.className = 'overlay';
  ov.innerHTML =
    '<div class="modal" role="dialog" aria-modal="true" aria-labelledby="edit-dialog-title">' +
      '<h3 id="edit-dialog-title">' + T.h_edit_db + '</h3>' +
      '<div class="form-grid">' +
        '<div class="form-group"><label>' + T.conn_name + '</label><input id="e-name" value="' + escAttr(name) + '"></div>' +
        '<div class="form-group"><label>' + T.db_name + '</label><input id="e-db" value="' + escAttr(p.db) + '"></div>' +
        '<div class="form-group"><label>' + T.server + '</label><input id="e-host" value="' + escAttr(p.host) + '"></div>' +
        '<div class="form-group"><label>' + T.port + '</label><input id="e-port" value="' + escAttr(p.port) + '"></div>' +
        '<div class="form-group"><label>' + T.login + '</label><input id="e-user" value="' + escAttr(p.user) + '"></div>' +
        '<div class="form-group"><label>' + T.password + '</label><input id="e-pass" type="password" value="' + escAttr(p.pass) + '"></div>' +
        '<div class="form-group full" style="margin-top:2px">' +
          '<label class="toggle">' +
            '<input type="checkbox" id="e-write" ' + (accessMode === 'unrestricted' ? 'checked' : '') + '>' +
            '<span class="toggle-track"></span>' +
            T.allow_write +
          '</label>' +
        '</div>' +
      '</div>' +
      '<div class="modal-actions">' +
        '<button class="btn" onclick="this.closest(\'.overlay\').remove()">' + T.btn_cancel + '</button>' +
        '<button class="btn" onclick="saveEdit(\'' + escAttr(name) + '\')">' + T.btn_save + '</button>' +
      '</div>' +
    '</div>';

  document.body.appendChild(ov);
  ov.addEventListener('click', function(e) { if (e.target === ov) ov.remove(); });
}

async function saveEdit(oldName) {
  const newName = document.getElementById('e-name').value.trim();
  const db   = document.getElementById('e-db').value.trim();
  const host = document.getElementById('e-host').value.trim();
  const port = document.getElementById('e-port').value.trim() || '5432';
  const user = document.getElementById('e-user').value.trim();
  const pass = document.getElementById('e-pass').value;
  const write = document.getElementById('e-write').checked;

  if (!newName || !host || !db || !user) { toast(T.fill_fields, true); return; }

  const uri = buildUri(host, port, db, user, pass);
  const r = await api('/api/edit', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ old_name: oldName, name: newName, uri: uri, access_mode: write ? 'unrestricted' : 'restricted' })
  });

  if (r && r.error) {
    // Error — don't close modal, show toast
    toast(T.msg_error + ': ' + r.error, true);
    return;
  }

  document.querySelector('.overlay').remove();
  toast(T.msg_saved + ': ' + newName);
  loadDatabases();
}

/* ═══ DELETE (confirmation modal, 1C-style) ═══ */
function confirmDelete(name) {
  var ov = document.createElement('div');
  ov.className = 'overlay';
  ov.innerHTML =
    '<div class="modal" role="dialog" aria-modal="true" aria-labelledby="delete-dialog-title" aria-describedby="delete-dialog-text" style="width:360px;text-align:center">' +
      '<h3 id="delete-dialog-title">' + T.confirm_delete + ' "' + escHtml(name) + '"?</h3>' +
      '<p id="delete-dialog-text" style="font-size:.82rem;margin-bottom:14px">' + T.confirm_delete_text + '</p>' +
      '<div style="display:flex;gap:6px;justify-content:center">' +
        '<button class="btn" onclick="this.closest(\'.overlay\').remove()">' + T.btn_cancel + '</button>' +
        '<button class="btn btn-ds" onclick="doDelete(\'' + escAttr(name) + '\')">' + T.btn_delete + '</button>' +
      '</div>' +
    '</div>';
  document.body.appendChild(ov);
  ov.addEventListener('click', function(e) { if (e.target === ov) ov.remove(); });
}

async function doDelete(name) {
  document.querySelector('.overlay').remove();
  const r = await api('/api/disconnect', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ name: name })
  });
  if (r && r.error) { toast(T.msg_error + ': ' + r.error, true); }
  else { toast(T.msg_disconnected + ': ' + name); }
  loadDatabases();
}

loadDatabases();
</script>
<div class="footer">
postgres-mcp-universal &mdash;
<a href="https://github.com/AlekseiSeleznev/postgres-mcp-universal">GitHub</a> &mdash;
<a href="https://github.com/AlekseiSeleznev/postgres-mcp-universal/blob/main/LICENSE">MIT License</a>
</div>
</body>
</html>"""


# ── Documentation page ──────────────────────────────────────────────
_DOC_STYLE = """body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;background:#0f172a;color:#e2e8f0;padding:20px;max-width:900px;margin:0 auto;line-height:1.6;font-size:.88rem}
a{color:#38bdf8;text-decoration:none}a:hover{text-decoration:underline}
h1{font-size:1.3rem;margin-bottom:4px}h2{font-size:1rem;margin-top:24px;margin-bottom:8px;color:#f8fafc;border-bottom:1px solid #334155;padding-bottom:4px}
h3{font-size:.88rem;margin-top:16px;margin-bottom:4px;color:#cbd5e1}
.sub{color:#64748b;font-size:.78rem}
code{background:#1e293b;padding:1px 5px;border-radius:3px;font-size:.82rem;color:#38bdf8}
pre{background:#1e293b;padding:12px;border-radius:6px;overflow-x:auto;font-size:.8rem;border:1px solid #334155;margin:8px 0}
pre code{background:none;padding:0;color:#e2e8f0}
table{width:100%;border-collapse:collapse;margin:8px 0;font-size:.82rem}
th{text-align:left;padding:6px 8px;border-bottom:1px solid #334155;color:#94a3b8;font-size:.72rem;text-transform:uppercase}
td{padding:6px 8px;border-bottom:1px solid rgba(51,65,85,.4)}
td code{font-size:.78rem}
.back{display:inline-block;margin-bottom:16px;font-size:.82rem}
ul{margin:4px 0 4px 20px}li{margin:2px 0}"""

DOCS_HTML = {
    "ru": """<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>postgres-mcp-universal — Документация</title><style>""" + _DOC_STYLE + """</style></head><body>
<a class="back" href="/dashboard?lang=ru">&larr; Dashboard</a>
<h1>postgres-mcp-universal</h1>
<div class="sub">MCP-шлюз для PostgreSQL &middot; <a href="https://github.com/AlekseiSeleznev/postgres-mcp-universal">GitHub</a> &middot; MIT License</div>

<h2>Оглавление</h2>
<ul>
<li><a href="#s1">1. Обзор</a></li>
<li><a href="#s2">2. Установка</a></li>
<li><a href="#s3">3. Подключение любого MCP-клиента</a></li>
<li><a href="#s4">4. Подключение через Codex</a></li>
<li><a href="#s5">5. Dashboard</a></li>
<li><a href="#s6">6. MCP Tools</a></li>
<li><a href="#s7">7. Конфигурация</a></li>
<li><a href="#s8">8. API Endpoints</a></li>
<li><a href="#s9">9. Проверка установки</a></li>
</ul>

<h2 id="s1">1. Обзор</h2>
<p>HTTP MCP-шлюз для PostgreSQL с dashboard, 23 MCP tools и Streamable HTTP transport на <code>POST /mcp</code>. Актуальный релиз документации: <code>v""" + __version__ + """</code>.</p>
<ul>
<li>Multi-database — несколько PostgreSQL серверов одновременно</li>
<li>Per-session routing — каждая MCP-сессия работает со своей активной базой</li>
<li>23 MCP tools — управление, запросы, схема, расширенный мониторинг</li>
<li>Dashboard — веб-интерфейс на <code>/dashboard</code></li>
<li>Единый Docker deployment path на bridge-сети с явным пробросом порта</li>
<li>Автогенерируемый каталог инструментов: <code>docs/mcp-tool-catalog.md</code></li>
</ul>

<h2 id="s2">2. Установка</h2>
<h3>Linux / macOS / Git Bash / WSL2</h3>
<pre><code>git clone https://github.com/AlekseiSeleznev/postgres-mcp-universal.git
cd postgres-mcp-universal
./setup.sh</code></pre>
<h3>Windows PowerShell</h3>
<pre><code>git clone https://github.com/AlekseiSeleznev/postgres-mcp-universal.git
cd postgres-mcp-universal
.\\install.cmd</code></pre>
<p>Установщики создают <code>.env</code>, оставляют <code>PG_MCP_API_KEY</code> пустым для no-auth режима по умолчанию, удаляют legacy override от старых host-networking версий, выполняют <code>docker compose up -d --build --remove-orphans</code> и ждут успешный ответ <code>/health</code>.</p>
<p>На Linux <code>setup.sh</code> дополнительно пытается установить systemd unit без forced rebuild на каждый старт. На Windows рекомендуется <code>install.cmd</code>, который запускает <code>install.ps1</code> через <code>ExecutionPolicy Bypass</code>. Для non-interactive проверки install-flow используйте <code>MCP_SETUP_CI=1 ./setup.sh</code>.</p>
<p>Dashboard: <code>http://localhost:8090/dashboard</code></p>

<h2 id="s3">3. Подключение любого MCP-клиента</h2>
<p>Сервер клиент-агностичен. Любому MCP-клиенту нужен только HTTP transport:</p>
<ul>
<li>endpoint: <code>POST http://localhost:8090/mcp</code></li>
<li>transport: Streamable HTTP</li>
<li>auth: по умолчанию выключен; при ручном включении нужен Bearer header с <code>PG_MCP_API_KEY</code></li>
</ul>
<p>Пустой <code>POST</code> на <code>/mcp</code> должен вернуть транспортный ответ MCP-сервера, а не <code>404</code>.</p>

<h2 id="s4">4. Подключение через Codex</h2>
<p>Если <code>codex</code> CLI доступен в <code>PATH</code>, <code>setup.sh</code> и <code>install.ps1</code> пытаются зарегистрировать MCP server автоматически. Ручная команда:</p>
<pre><code>codex mcp remove postgres-universal >/dev/null 2>&1 || true
codex mcp add postgres-universal --url http://localhost:8090/mcp
codex mcp get postgres-universal</code></pre>
<p>Если вы вручную включили <code>PG_MCP_API_KEY</code>, экспортируйте ту же переменную в окружение Codex и используйте <code>--bearer-token-env-var PG_MCP_API_KEY</code>.</p>

<h2 id="s5">5. Dashboard</h2>
<p>Веб-интерфейс для управления подключениями:</p>
<ul>
<li>Подключение и отключение баз данных</li>
<li>Редактирование параметров подключения</li>
<li>Переключение базы по умолчанию</li>
<li>Режим Read/Write или Read-only per-database</li>
<li>Двуязычный интерфейс (RU/EN)</li>
<li>Bearer token не встраивается в HTML; браузер запрашивает его только после 401, если включён <code>PG_MCP_API_KEY</code></li>
</ul>

<h2 id="s6">6. MCP Tools</h2>
<h3>Управление базами данных</h3>
<table><tr><th>Tool</th><th>Описание</th></tr>
<tr><td><code>connect_database</code></td><td>Подключиться к PostgreSQL; принимает <code>uri</code> или alias <code>connection_string</code></td></tr>
<tr><td><code>disconnect_database</code></td><td>Отключиться от базы</td></tr>
<tr><td><code>switch_database</code></td><td>Переключить активную базу для сессии</td></tr>
<tr><td><code>list_databases</code></td><td>Список зарегистрированных баз</td></tr>
<tr><td><code>get_server_status</code></td><td>Статус gateway: пулы, сессии, активная база</td></tr>
</table>

<h3>Запросы</h3>
<table><tr><th>Tool</th><th>Описание</th></tr>
<tr><td><code>execute_sql</code></td><td>Выполнить SQL; в restricted режиме разрешены только read-only запросы</td></tr>
<tr><td><code>explain_query</code></td><td>EXPLAIN ANALYZE с планом выполнения (JSON, BUFFERS)</td></tr>
</table>

<h3>Навигация по схеме</h3>
<table><tr><th>Tool</th><th>Описание</th></tr>
<tr><td><code>list_schemas</code></td><td>Список схем с количеством таблиц</td></tr>
<tr><td><code>list_tables</code></td><td>Таблицы и views с размерами</td></tr>
<tr><td><code>get_table_info</code></td><td>Колонки, PK, FK, индексы, размеры</td></tr>
<tr><td><code>list_indexes</code></td><td>Индексы со статистикой использования</td></tr>
<tr><td><code>list_functions</code></td><td>Функции и процедуры</td></tr>
</table>

<h3>Мониторинг</h3>
<table><tr><th>Tool</th><th>Описание</th></tr>
<tr><td><code>db_health</code></td><td>Версия, аптайм, подключения, cache ratio, deadlocks</td></tr>
<tr><td><code>active_queries</code></td><td>Текущие запросы с длительностью и wait events</td></tr>
<tr><td><code>table_bloat</code></td><td>Оценка bloat (dead tuples)</td></tr>
<tr><td><code>vacuum_stats</code></td><td>Статистика vacuum/autovacuum</td></tr>
<tr><td><code>lock_info</code></td><td>Блокировки и blocked queries</td></tr>
</table>

<h3>Расширенный мониторинг</h3>
<table><tr><th>Tool</th><th>Описание</th></tr>
<tr><td><code>pg_overview</code></td><td>Сводка по серверу: версия, аптайм, cache hit, checkpoints, WAL</td></tr>
<tr><td><code>pg_activity</code></td><td>Текущая активность backend-процессов и blocked/blocking пары</td></tr>
<tr><td><code>pg_table_stats</code></td><td>Статистика таблиц по схемам: размеры, live/dead tuples, patterns</td></tr>
<tr><td><code>pg_index_stats</code></td><td>Статистика индексов: scan count, tuples read/fetched, размер</td></tr>
<tr><td><code>pg_replication</code></td><td>Состояние репликации: lag, LSN, replication slots</td></tr>
<tr><td><code>pg_schemas</code></td><td>Пользовательские схемы с количеством таблиц</td></tr>
</table>

<h2 id="s7">7. Конфигурация</h2>
<p>Через <code>.env</code> или переменные окружения:</p>
<table><tr><th>Переменная</th><th>По умолчанию</th><th>Описание</th></tr>
<tr><td><code>PG_MCP_PORT</code></td><td>8090</td><td>Порт сервера</td></tr>
<tr><td><code>PG_MCP_LOG_LEVEL</code></td><td>INFO</td><td>Уровень логирования</td></tr>
<tr><td><code>PG_MCP_DATABASE_URI</code></td><td>—</td><td>URI для авто-подключения</td></tr>
<tr><td><code>PG_MCP_ACCESS_MODE</code></td><td>unrestricted</td><td>Режим доступа по умолчанию</td></tr>
<tr><td><code>PG_MCP_QUERY_TIMEOUT</code></td><td>30</td><td>Таймаут запросов (сек)</td></tr>
<tr><td><code>PG_MCP_POOL_MIN_SIZE</code></td><td>2</td><td>Мин. размер пула</td></tr>
<tr><td><code>PG_MCP_POOL_MAX_SIZE</code></td><td>10</td><td>Макс. размер пула</td></tr>
<tr><td><code>PG_MCP_METADATA_CACHE_TTL</code></td><td>600</td><td>TTL кэша метаданных (сек)</td></tr>
<tr><td><code>PG_MCP_SESSION_TIMEOUT</code></td><td>28800</td><td>Таймаут неактивной сессии (сек)</td></tr>
<tr><td><code>PG_MCP_API_KEY</code></td><td>—</td><td>Bearer token для MCP и dashboard API (пусто = auth выключен; установщики оставляют пустым по умолчанию)</td></tr>
<tr><td><code>PG_MCP_RATE_LIMIT_ENABLED</code></td><td>true</td><td>Включает in-memory rate limiting для <code>/mcp</code>, <code>/api/*</code> и <code>/oauth/token</code></td></tr>
<tr><td><code>PG_MCP_RATE_LIMIT_WINDOW_SECONDS</code></td><td>60</td><td>Окно rate limiting в секундах</td></tr>
<tr><td><code>PG_MCP_RATE_LIMIT_MCP_REQUESTS</code></td><td>60</td><td>Лимит запросов к <code>/mcp</code> на IP в одном окне</td></tr>
<tr><td><code>PG_MCP_RATE_LIMIT_API_REQUESTS</code></td><td>60</td><td>Лимит запросов к <code>/api/*</code> на IP в одном окне</td></tr>
<tr><td><code>PG_MCP_RATE_LIMIT_OAUTH_REQUESTS</code></td><td>10</td><td>Лимит запросов к <code>/oauth/token</code> на IP в одном окне</td></tr>
<tr><td><code>PG_MCP_ENABLE_SIMPLE_TOKEN_ENDPOINT</code></td><td>false</td><td>Совместимый <code>/oauth/token</code> endpoint, требует <code>client_secret</code></td></tr>
<tr><td><code>PG_MCP_STATE_FILE</code></td><td>/data/db_state.json</td><td>Путь к файлу состояния подключённых баз</td></tr>
</table>
<p>Для локальной отладки limiter можно отключить через <code>PG_MCP_RATE_LIMIT_ENABLED=false</code>. При превышении лимита сервер возвращает <code>429</code> и заголовок <code>Retry-After</code>.</p>

<h2 id="s8">8. API Endpoints</h2>
<table><tr><th>Endpoint</th><th>Метод</th><th>Описание</th></tr>
<tr><td><code>/mcp</code></td><td>POST</td><td>MCP Streamable HTTP transport</td></tr>
<tr><td><code>/health</code></td><td>GET</td><td>Health check и статус пулов</td></tr>
<tr><td><code>/dashboard</code></td><td>GET</td><td>Веб-интерфейс</td></tr>
<tr><td><code>/dashboard/docs</code></td><td>GET</td><td>Встроенная документация</td></tr>
<tr><td><code>/api/databases</code></td><td>GET</td><td>Список баз; auth требуется только если задан <code>PG_MCP_API_KEY</code></td></tr>
<tr><td><code>/api/connect</code></td><td>POST</td><td>Подключить базу</td></tr>
<tr><td><code>/api/disconnect</code></td><td>POST</td><td>Отключить базу</td></tr>
<tr><td><code>/api/edit</code></td><td>POST</td><td>Редактировать подключение</td></tr>
<tr><td><code>/api/switch</code></td><td>POST</td><td>Переключить активную базу</td></tr>
<tr><td><code>/.well-known/oauth-protected-resource</code></td><td>GET</td><td>RFC 9728 metadata</td></tr>
<tr><td><code>/.well-known/oauth-authorization-server</code></td><td>GET</td><td>RFC 8414 metadata</td></tr>
<tr><td><code>/oauth/token</code></td><td>POST</td><td>Совместимый token endpoint, по умолчанию выключен</td></tr>
</table>

<h2 id="s9">9. Проверка установки</h2>
<ul>
<li><code>curl http://localhost:8090/health</code></li>
<li><code>curl -X POST http://localhost:8090/mcp</code></li>
<li><code>http://localhost:8090/dashboard</code></li>
<li><code>codex mcp get postgres-universal</code> — только если вы используете Codex</li>
<li>Linux CI выполняет runtime smoke через <code>MCP_SETUP_CI=1 ./setup.sh</code></li>
<li>Windows CI выполняет статические install checks для <code>install.ps1</code> и <code>uninstall.ps1</code>; runtime smoke нужно повторять вручную на чистой Windows-машине</li>
</ul>
</body></html>""",

    "en": """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>postgres-mcp-universal — Documentation</title><style>""" + _DOC_STYLE + """</style></head><body>
<a class="back" href="/dashboard?lang=en">&larr; Dashboard</a>
<h1>postgres-mcp-universal</h1>
<div class="sub">MCP gateway for PostgreSQL &middot; <a href="https://github.com/AlekseiSeleznev/postgres-mcp-universal">GitHub</a> &middot; MIT License</div>

<h2>Contents</h2>
<ul>
<li><a href="#e1">1. Overview</a></li>
<li><a href="#e2">2. Install</a></li>
<li><a href="#e3">3. Connect Any MCP Client</a></li>
<li><a href="#e4">4. Connect to Codex</a></li>
<li><a href="#e5">5. Dashboard</a></li>
<li><a href="#e6">6. MCP Tools</a></li>
<li><a href="#e7">7. Configuration</a></li>
<li><a href="#e8">8. API Endpoints</a></li>
<li><a href="#e9">9. Installation Verification</a></li>
</ul>

<h2 id="e1">1. Overview</h2>
<p>HTTP MCP gateway for PostgreSQL with a dashboard, 23 MCP tools, and Streamable HTTP transport on <code>POST /mcp</code>. Current documented release: <code>v""" + __version__ + """</code>.</p>
<ul>
<li>Multi-database — multiple PostgreSQL servers at once</li>
<li>Per-session routing — each MCP session works with its own active database</li>
<li>23 MCP tools — admin, queries, schema, and advanced monitoring</li>
<li>Dashboard — web UI at <code>/dashboard</code></li>
<li>Unified Docker deployment path on bridge networking with explicit port publishing</li>
<li>Autogenerated tool catalog: <code>docs/mcp-tool-catalog.md</code></li>
</ul>

<h2 id="e2">2. Install</h2>
<h3>Linux / macOS / Git Bash / WSL2</h3>
<pre><code>git clone https://github.com/AlekseiSeleznev/postgres-mcp-universal.git
cd postgres-mcp-universal
./setup.sh</code></pre>
<h3>Windows PowerShell</h3>
<pre><code>git clone https://github.com/AlekseiSeleznev/postgres-mcp-universal.git
cd postgres-mcp-universal
.\\install.cmd</code></pre>
<p>The installers create <code>.env</code>, keep <code>PG_MCP_API_KEY</code> empty for the default no-auth path, remove legacy overrides from pre-bridge releases, run <code>docker compose up -d --build --remove-orphans</code>, and wait for <code>/health</code>.</p>
<p>On Linux, <code>setup.sh</code> also tries to install a systemd unit without rebuilding on every restart. On Windows, <code>install.cmd</code> is the recommended path because it starts <code>install.ps1</code> with <code>ExecutionPolicy Bypass</code>. For a non-interactive install-flow check, use <code>MCP_SETUP_CI=1 ./setup.sh</code>.</p>
<p>Dashboard: <code>http://localhost:8090/dashboard</code></p>

<h2 id="e3">3. Connect Any MCP Client</h2>
<p>The server itself is client-agnostic. Any MCP client only needs the HTTP transport endpoint:</p>
<ul>
<li>endpoint: <code>POST http://localhost:8090/mcp</code></li>
<li>transport: Streamable HTTP</li>
<li>auth: disabled by default; if you enable it manually, send a Bearer token with <code>PG_MCP_API_KEY</code></li>
</ul>
<p>An empty <code>POST</code> to <code>/mcp</code> should return an MCP transport response, not <code>404</code>.</p>

<h2 id="e4">4. Connect to Codex</h2>
<p>If the <code>codex</code> CLI is available in <code>PATH</code>, <code>setup.sh</code> and <code>install.ps1</code> try to register the MCP server automatically. Manual commands:</p>
<pre><code>codex mcp remove postgres-universal >/dev/null 2>&1 || true
codex mcp add postgres-universal --url http://localhost:8090/mcp
codex mcp get postgres-universal</code></pre>
<p>If you enable <code>PG_MCP_API_KEY</code> manually, export the same variable into the Codex environment and use <code>--bearer-token-env-var PG_MCP_API_KEY</code>.</p>

<h2 id="e5">5. Dashboard</h2>
<p>Web interface for connection management:</p>
<ul>
<li>Connect and disconnect databases</li>
<li>Edit connection parameters</li>
<li>Switch the default database</li>
<li>Read/Write or Read-only mode per database</li>
<li>Bilingual UI (RU/EN)</li>
<li>The Bearer token is never embedded into HTML; the browser asks for it only after a 401 when <code>PG_MCP_API_KEY</code> is enabled</li>
</ul>

<h2 id="e6">6. MCP Tools</h2>
<h3>Database Management</h3>
<table><tr><th>Tool</th><th>Description</th></tr>
<tr><td><code>connect_database</code></td><td>Connect to PostgreSQL; accepts <code>uri</code> or the <code>connection_string</code> alias</td></tr>
<tr><td><code>disconnect_database</code></td><td>Disconnect from a database</td></tr>
<tr><td><code>switch_database</code></td><td>Switch the active database for the session</td></tr>
<tr><td><code>list_databases</code></td><td>List registered databases</td></tr>
<tr><td><code>get_server_status</code></td><td>Gateway status: pools, sessions, active database</td></tr>
</table>

<h3>Queries</h3>
<table><tr><th>Tool</th><th>Description</th></tr>
<tr><td><code>execute_sql</code></td><td>Execute SQL; restricted mode allows only read-only queries</td></tr>
<tr><td><code>explain_query</code></td><td>EXPLAIN ANALYZE with execution plan (JSON, BUFFERS)</td></tr>
</table>

<h3>Schema Navigation</h3>
<table><tr><th>Tool</th><th>Description</th></tr>
<tr><td><code>list_schemas</code></td><td>List schemas with table counts</td></tr>
<tr><td><code>list_tables</code></td><td>Tables and views with sizes</td></tr>
<tr><td><code>get_table_info</code></td><td>Columns, PK, FK, indexes, sizes</td></tr>
<tr><td><code>list_indexes</code></td><td>Indexes with usage statistics</td></tr>
<tr><td><code>list_functions</code></td><td>Functions and procedures</td></tr>
</table>

<h3>Monitoring</h3>
<table><tr><th>Tool</th><th>Description</th></tr>
<tr><td><code>db_health</code></td><td>Version, uptime, connections, cache ratio, deadlocks</td></tr>
<tr><td><code>active_queries</code></td><td>Running queries with duration and wait events</td></tr>
<tr><td><code>table_bloat</code></td><td>Bloat estimation (dead tuples)</td></tr>
<tr><td><code>vacuum_stats</code></td><td>Vacuum/autovacuum statistics</td></tr>
<tr><td><code>lock_info</code></td><td>Locks and blocked queries</td></tr>
</table>

<h3>Advanced Monitoring</h3>
<table><tr><th>Tool</th><th>Description</th></tr>
<tr><td><code>pg_overview</code></td><td>Server snapshot: version, uptime, cache hit, checkpoints, WAL</td></tr>
<tr><td><code>pg_activity</code></td><td>Backend activity with blocked/blocking query pairs</td></tr>
<tr><td><code>pg_table_stats</code></td><td>Per-table stats by schema: sizes, live/dead tuples, scan patterns</td></tr>
<tr><td><code>pg_index_stats</code></td><td>Index usage metrics: scans, tuples read/fetched, size</td></tr>
<tr><td><code>pg_replication</code></td><td>Replication state: lag, LSN positions, replication slots</td></tr>
<tr><td><code>pg_schemas</code></td><td>User-defined schemas with table counts</td></tr>
</table>

<h2 id="e7">7. Configuration</h2>
<p>Via <code>.env</code> or environment variables:</p>
<table><tr><th>Variable</th><th>Default</th><th>Description</th></tr>
<tr><td><code>PG_MCP_PORT</code></td><td>8090</td><td>Server port</td></tr>
<tr><td><code>PG_MCP_LOG_LEVEL</code></td><td>INFO</td><td>Log level</td></tr>
<tr><td><code>PG_MCP_DATABASE_URI</code></td><td>—</td><td>Auto-connect URI on startup</td></tr>
<tr><td><code>PG_MCP_ACCESS_MODE</code></td><td>unrestricted</td><td>Default access mode</td></tr>
<tr><td><code>PG_MCP_QUERY_TIMEOUT</code></td><td>30</td><td>Query timeout (seconds)</td></tr>
<tr><td><code>PG_MCP_POOL_MIN_SIZE</code></td><td>2</td><td>Min pool size</td></tr>
<tr><td><code>PG_MCP_POOL_MAX_SIZE</code></td><td>10</td><td>Max pool size</td></tr>
<tr><td><code>PG_MCP_METADATA_CACHE_TTL</code></td><td>600</td><td>Metadata cache TTL (seconds)</td></tr>
<tr><td><code>PG_MCP_SESSION_TIMEOUT</code></td><td>28800</td><td>Idle session timeout (seconds)</td></tr>
<tr><td><code>PG_MCP_API_KEY</code></td><td>—</td><td>Bearer token for MCP and dashboard API (empty = auth disabled; installers keep it empty by default)</td></tr>
<tr><td><code>PG_MCP_RATE_LIMIT_ENABLED</code></td><td>true</td><td>Enables in-memory rate limiting for <code>/mcp</code>, <code>/api/*</code>, and <code>/oauth/token</code></td></tr>
<tr><td><code>PG_MCP_RATE_LIMIT_WINDOW_SECONDS</code></td><td>60</td><td>Rate limiting window in seconds</td></tr>
<tr><td><code>PG_MCP_RATE_LIMIT_MCP_REQUESTS</code></td><td>60</td><td>Per-IP request limit for <code>/mcp</code> within one window</td></tr>
<tr><td><code>PG_MCP_RATE_LIMIT_API_REQUESTS</code></td><td>60</td><td>Per-IP request limit for <code>/api/*</code> within one window</td></tr>
<tr><td><code>PG_MCP_RATE_LIMIT_OAUTH_REQUESTS</code></td><td>10</td><td>Per-IP request limit for <code>/oauth/token</code> within one window</td></tr>
<tr><td><code>PG_MCP_ENABLE_SIMPLE_TOKEN_ENDPOINT</code></td><td>false</td><td>Compatibility <code>/oauth/token</code> endpoint; requires <code>client_secret</code></td></tr>
<tr><td><code>PG_MCP_STATE_FILE</code></td><td>/data/db_state.json</td><td>Path to the persisted state file for registered databases</td></tr>
</table>
<p>For local debugging, you can disable the limiter with <code>PG_MCP_RATE_LIMIT_ENABLED=false</code>. When a limit is exceeded, the server returns <code>429</code> with a <code>Retry-After</code> header.</p>

<h2 id="e8">8. API Endpoints</h2>
<table><tr><th>Endpoint</th><th>Method</th><th>Description</th></tr>
<tr><td><code>/mcp</code></td><td>POST</td><td>MCP Streamable HTTP transport</td></tr>
<tr><td><code>/health</code></td><td>GET</td><td>Health check and pool status</td></tr>
<tr><td><code>/dashboard</code></td><td>GET</td><td>Web UI</td></tr>
<tr><td><code>/dashboard/docs</code></td><td>GET</td><td>Built-in documentation</td></tr>
<tr><td><code>/api/databases</code></td><td>GET</td><td>List databases; auth is required only if <code>PG_MCP_API_KEY</code> is set</td></tr>
<tr><td><code>/api/connect</code></td><td>POST</td><td>Connect a database</td></tr>
<tr><td><code>/api/disconnect</code></td><td>POST</td><td>Disconnect a database</td></tr>
<tr><td><code>/api/edit</code></td><td>POST</td><td>Edit a connection</td></tr>
<tr><td><code>/api/switch</code></td><td>POST</td><td>Switch the active database</td></tr>
<tr><td><code>/.well-known/oauth-protected-resource</code></td><td>GET</td><td>RFC 9728 metadata</td></tr>
<tr><td><code>/.well-known/oauth-authorization-server</code></td><td>GET</td><td>RFC 8414 metadata</td></tr>
<tr><td><code>/oauth/token</code></td><td>POST</td><td>Compatibility token endpoint; disabled by default</td></tr>
</table>

<h2 id="e9">9. Installation Verification</h2>
<ul>
<li><code>curl http://localhost:8090/health</code></li>
<li><code>curl -X POST http://localhost:8090/mcp</code></li>
<li><code>http://localhost:8090/dashboard</code></li>
<li><code>codex mcp get postgres-universal</code> — only if you use Codex</li>
<li>Linux CI runs a real runtime smoke with <code>MCP_SETUP_CI=1 ./setup.sh</code></li>
<li>Windows CI runs static install checks for <code>install.ps1</code> and <code>uninstall.ps1</code>; repeat runtime smoke manually on a clean Windows machine</li>
</ul>
</body></html>""",
}


def render_docs(lang: str = "ru") -> str:
    return DOCS_HTML.get(lang, DOCS_HTML["ru"])
