// MyMiniCloud Portal: SPA đăng nhập Keycloak theo Authorization Code + PKCE (RFC 7636), không dùng thư viện ngoài.
// Mọi request đều cùng origin (gateway định tuyến /auth/ tới Keycloak, /api/ tới Flask) nên không cần CORS.
'use strict';

const REALM = 'realm_523H0008_523H0025';
const CLIENT_ID = 'portal';
const OIDC = `${location.origin}/auth/realms/${REALM}/protocol/openid-connect`;
const REDIRECT_URI = `${location.origin}/portal/`;
const STORE = sessionStorage;            // token chỉ sống trong tab hiện tại

const $ = (id) => document.getElementById(id);
const show = (el, on = true) => { el.hidden = !on; };
const icon = (name, cls = 'ic') => window.mmcIcon(name, cls);   // from /assets/shell.js
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}
function emptyRow(cols, iconName, text, cls = '') {
  const tr = el('tr');
  const td = el('td', `empty ${cls}`);
  td.colSpan = cols;
  td.append(icon(iconName), document.createTextNode(text));
  tr.append(td);
  return tr;
}

// ---------------------------------------------------------------- PKCE và token
function b64url(bytes) {
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
function randomString(n = 32) { return b64url(crypto.getRandomValues(new Uint8Array(n))); }
async function sha256(text) {
  return new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)));
}
function decodeJwt(token) {
  const part = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
  const json = decodeURIComponent(atob(part).split('').map(c => '%' + c.charCodeAt(0).toString(16).padStart(2, '0')).join(''));
  return JSON.parse(json);
}

async function login() {
  if (!window.crypto || !crypto.subtle) {
    showLoginError('Trình duyệt chỉ cho dùng Web Crypto trên HTTPS hoặc localhost. Hãy mở Portal qua https:// hoặc http://localhost.');
    return;
  }
  const verifier = randomString(48);
  const state = randomString(16);
  const challenge = b64url(await sha256(verifier));
  STORE.setItem('pkce', JSON.stringify({ verifier, state }));
  const params = new URLSearchParams({
    client_id: CLIENT_ID, response_type: 'code', scope: 'openid profile email',
    redirect_uri: REDIRECT_URI, state, code_challenge: challenge, code_challenge_method: 'S256',
  });
  location.assign(`${OIDC}/auth?${params}`);
}

async function tokenRequest(body) {
  const res = await fetch(`${OIDC}/token`, { method: 'POST', body: new URLSearchParams(body) });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error_description || data.error || `HTTP ${res.status}`);
  const now = Math.floor(Date.now() / 1000);
  STORE.setItem('tokens', JSON.stringify({
    access: data.access_token, refresh: data.refresh_token, id: data.id_token,
    expiresAt: now + data.expires_in, refreshExpiresAt: now + (data.refresh_expires_in || 0),
  }));
}

// Quay lại từ Keycloak với ?code=...&state=...
async function handleCallback() {
  const q = new URLSearchParams(location.search);
  if (q.has('error')) throw new Error(q.get('error_description') || q.get('error'));
  if (!q.has('code')) return;
  const saved = JSON.parse(STORE.getItem('pkce') || '{}');
  STORE.removeItem('pkce');
  history.replaceState({}, '', REDIRECT_URI);
  if (!saved.state || q.get('state') !== saved.state) throw new Error('Tham số state không khớp (có thể là request giả mạo)');
  await tokenRequest({
    grant_type: 'authorization_code', client_id: CLIENT_ID, code: q.get('code'),
    redirect_uri: REDIRECT_URI, code_verifier: saved.verifier,
  });
}

function tokens() { return JSON.parse(STORE.getItem('tokens') || 'null'); }

// Access token Keycloak sống 5 phút: làm mới bằng refresh token khi còn dưới 30 giây
async function accessToken() {
  const t = tokens();
  if (!t) return null;
  const now = Math.floor(Date.now() / 1000);
  if (t.expiresAt - now > 30) return t.access;
  if (t.refresh && t.refreshExpiresAt - now > 10) {
    await tokenRequest({ grant_type: 'refresh_token', client_id: CLIENT_ID, refresh_token: t.refresh });
    return tokens().access;
  }
  STORE.removeItem('tokens');
  return null;
}

function logout() {
  const t = tokens();
  STORE.removeItem('tokens');
  const params = new URLSearchParams({ client_id: CLIENT_ID, post_logout_redirect_uri: REDIRECT_URI });
  if (t && t.id) params.set('id_token_hint', t.id);
  location.assign(`${OIDC}/logout?${params}`);
}

// ---------------------------------------------------------------- Gọi API và ghi nhật ký
async function api(method, path, body, { raw = false } = {}) {
  const token = await accessToken();
  if (!token) { location.reload(); throw new Error('Phiên đăng nhập đã hết'); }
  const headers = { Authorization: `Bearer ${token}` };
  let payload;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body); }
  const t0 = performance.now();
  const res = await fetch(`/api${path}`, { method, headers, body: payload });
  logCall(method, path, res.status, performance.now() - t0, res.headers.get('X-Request-ID'));
  if (raw) return res;
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    const err = new Error((data && data.error) || `HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

function logCall(method, path, status, ms, requestId) {
  const tr = el('tr');
  const badge = el('span', `badge ${status >= 500 ? 'badge-err' : status >= 400 ? 'badge-warn' : 'badge-ok'}`, String(status));
  const code = el('td');
  code.append(badge);
  tr.append(el('td', 'nowrap', new Date().toLocaleTimeString('vi-VN')), el('td', 'mono', `${method} /api${path}`),
    code, el('td', 'num', `${ms.toFixed(0)} ms`), el('td', 'mono small', requestId || ''));
  const body = $('calls-body');
  body.prepend(tr);
  while (body.children.length > 12) body.lastChild.remove();
}

function toast(text, kind = 'ok') {
  const box = $('toast');
  box.replaceChildren();
  if (kind === 'ok') box.append(icon('check', 'ic check'));
  box.append(el('span', '', text));
  box.className = `msg msg-${kind}`;
  show(box);
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => {
    box.classList.add('leaving');
    setTimeout(() => show(box, false), 160);
  }, 4000);
}
const { flash, shake, countUp } = window.mmc;     // motion helpers from /assets/shell.js

// Placeholder rows with a light sweep while a table is loading
function skeletonRows(body, cols, n = 4) {
  body.replaceChildren();
  for (let i = 0; i < n; i++) {
    const tr = el('tr', 'skel');
    for (let c = 0; c < cols; c++) {
      const td = el('td');
      const bar = el('span', 'skeleton');
      bar.style.width = `${40 + ((i * 7 + c * 13) % 50)}%`;
      td.append(bar);
      tr.append(td);
    }
    body.append(tr);
  }
}
function showError(e) {
  toast(e.status === 403 ? `Bị từ chối (403): ${e.message}` : `Lỗi: ${e.message}`, 'error');
}
function showLoginError(text) { const el = $('login-error'); el.textContent = text; show(el); }

// ---------------------------------------------------------------- Hồ sơ
let me = null;

async function loadProfile() {
  me = await api('GET', '/me');
  $('nav-user').replaceChildren(icon('user'), el('span', '', me.username));
  // Vietnamese names put the family name first (the Keycloak name claim puts the given name first)
  $('p-name').textContent = [me.family_name, me.given_name].filter(Boolean).join(' ') || me.name || me.username;
  $('p-username').textContent = me.username;
  $('p-email').textContent = me.email || '';
  $('p-roles').innerHTML = '';
  for (const r of me.roles.filter(r => ['editor', 'viewer'].includes(r))) {
    const b = document.createElement('span');
    b.className = `badge role-${r}`;
    b.textContent = r;
    $('p-roles').append(b, ' ');
  }
  $('p-issuer').textContent = me.issuer;
  $('p-aud').textContent = `${[].concat(me.audience).join(', ')} / ${me.client}`;
  $('p-token').textContent = JSON.stringify(decodeJwt(tokens().access), null, 2);
  setAvatar(me.avatar_url);
  const editor = me.roles.includes('editor');
  $('students-note').className = editor ? 'alert' : 'alert alert-warn';
  $('students-note').textContent = editor
    ? 'Bạn có role editor: được thêm, sửa, xoá.'
    : 'Bạn chỉ có role viewer: nút ghi vẫn hiện để thấy server từ chối (403), quyền được kiểm tra ở Flask chứ không chỉ ở giao diện.';
}

function setAvatar(url) {
  show($('avatar'), !!url);
  show($('avatar-empty'), !url);
  if (url) $('avatar').src = url;
}

function tickExpiry() {
  const t = tokens();
  if (!t) return;
  const left = t.expiresAt - Math.floor(Date.now() / 1000);
  $('p-exp').textContent = left > 0 ? `${Math.floor(left / 60)} phút ${left % 60} giây (tự làm mới bằng refresh token)` : 'đã hết hạn';
  const claims = decodeJwt(t.access);
  const life = Math.max(1, claims.exp - claims.iat);
  const pct = Math.max(0, Math.min(100, (left / life) * 100));
  $('p-exp-bar').style.transform = `scaleX(${pct / 100})`;
  $('p-exp-bar').classList.toggle('low', pct < 25);
}

// Avatar drop zone: the <input type=file> covers the zone, so clicking and dropping both work natively
$('avatar-file').addEventListener('change', () => {
  const f = $('avatar-file').files[0];
  $('avatar-file-name').textContent = f ? `${f.name} · ${(f.size / 1024).toFixed(0)} KB` : 'Chọn hoặc kéo ảnh vào đây';
});
for (const [ev, on] of [['dragenter', true], ['dragover', true], ['dragleave', false], ['drop', false]]) {
  $('avatar-drop').addEventListener(ev, () => $('avatar-drop').classList.toggle('over', on));
}

$('btn-copy-token').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText($('p-token').textContent);
    toast('Đã sao chép payload của token');
  } catch (e) { toast('Trình duyệt không cho sao chép tự động', 'error'); }
});

$('form-avatar').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const file = $('avatar-file').files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  try {
    const r = await api('POST', '/avatar', fd);
    setAvatar(r.url);
    toast(`Đã lưu ${r.key} (${(r.bytes / 1024).toFixed(1)} KB) vào bucket ${r.bucket}`);
  } catch (e) { showError(e); }
});

// ---------------------------------------------------------------- Students (CRUD)
let students = [];

let changedId = null;     // id of the row just added or edited: flashed once after the table re-renders

async function loadStudents() {
  if (!students.length) skeletonRows($('students-body'), 6);
  const data = await api('GET', '/students');
  students = data.students;
  renderStudents();
}

function renderStudents() {
  const q = $('students-search').value.trim().toLowerCase();
  const rows = students.filter((s) => !q || [s.student_id, s.fullname, s.major || '', s.dob || '']
    .some((v) => String(v).toLowerCase().includes(q)));
  const body = $('students-body');
  body.replaceChildren();
  $('students-count').textContent = q ? `${rows.length} / ${students.length} sinh viên` : `${students.length} sinh viên`;
  if (!rows.length) {
    body.append(emptyRow(6, 'users', q ? 'Không có sinh viên khớp từ khoá.' : 'Chưa có sinh viên nào.'));
    return;
  }
  const editing = $('s-id').value;
  for (const s of rows) {
    const tr = el('tr', String(s.id) === editing ? 'editing' : '');
    tr.append(el('td', 'num', s.id), el('td', 'mono', s.student_id), el('td', '', s.fullname),
      el('td', 'nowrap', s.dob ? new Date(`${s.dob}T00:00:00`).toLocaleDateString('vi-VN') : ''), el('td', '', s.major || ''));
    const td = el('td', 'actions');
    const edit = el('button', 'btn btn-small', 'Sửa');
    const del = el('button', 'btn btn-small btn-danger', 'Xoá');
    edit.type = 'button';
    del.type = 'button';
    edit.onclick = () => startEdit(s);
    del.onclick = () => deleteStudent(s);
    td.append(edit, ' ', del);
    tr.append(td);
    tr.dataset.id = s.id;
    body.append(tr);
    if (String(s.id) === String(changedId)) flash(tr);
  }
  changedId = null;
}
$('students-search').addEventListener('input', renderStudents);

function startEdit(s) {
  $('s-id').value = s.id;
  $('s-student-id').value = s.student_id;
  $('s-fullname').value = s.fullname;
  $('s-dob').value = s.dob || '';
  $('s-major').value = s.major || '';
  $('btn-save-student').textContent = `Lưu #${s.id}`;
  $('form-title').textContent = `Sửa sinh viên #${s.id} (${s.student_id})`;
  show($('btn-cancel-edit'));
  renderStudents();
  $('form-student').scrollIntoView({ block: 'center', behavior: 'smooth' });
  $('s-fullname').focus({ preventScroll: true });
}
function resetForm() {
  $('form-student').reset();
  $('s-id').value = '';
  $('btn-save-student').textContent = 'Thêm';
  $('form-title').textContent = 'Thêm sinh viên';
  show($('btn-cancel-edit'), false);
  renderStudents();
}

$('form-student').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const id = $('s-id').value;
  const body = {
    student_id: $('s-student-id').value.trim(), fullname: $('s-fullname').value.trim(),
    dob: $('s-dob').value || null, major: $('s-major').value.trim(),
  };
  const btn = $('btn-save-student');
  btn.classList.add('busy');
  try {
    const s = id ? await api('PUT', `/students/${id}`, body) : await api('POST', '/students', body);
    toast(id ? `Đã cập nhật ${s.student_id}` : `Đã thêm ${s.student_id} (id ${s.id})`);
    changedId = s.id;
    resetForm();
    await loadStudents();
  } catch (e) {
    showError(e);
    // 400: point at the form fields; 403: point at the button the viewer is not allowed to use
    shake(e.status === 400 ? $('form-student') : btn);
  } finally {
    btn.classList.remove('busy');
  }
});
$('btn-cancel-edit').onclick = resetForm;
$('btn-reload-students').onclick = () => loadStudents().catch(showError);

// Confirmation uses a native modal <dialog> (focus trap, Esc to cancel) instead of window.confirm
function confirmDialog(text) {
  const dlg = $('confirm-dialog');
  $('confirm-text').textContent = text;
  dlg.returnValue = '';
  return new Promise((resolve) => {
    dlg.addEventListener('close', () => resolve(dlg.returnValue === 'ok'), { once: true });
    dlg.showModal();
    $('confirm-cancel').focus();
  });
}

async function deleteStudent(s) {
  if (!(await confirmDialog(`Sinh viên ${s.student_id} – ${s.fullname} sẽ bị xoá khỏi studentdb.students.`))) return;
  try {
    await api('DELETE', `/students/${s.id}`);
    const row = $('students-body').querySelector(`tr[data-id="${s.id}"]`);
    if (row && !window.mmc.reduceMotion()) {
      row.classList.add('leaving-row');
      await new Promise((r) => setTimeout(r, 220));
    }
    toast(`Đã xoá ${s.student_id}`);
    if ($('s-id').value === String(s.id)) resetForm();
    await loadStudents();
  } catch (e) {
    showError(e);
    shake($('students-body').querySelector(`tr[data-id="${s.id}"]`));
  }
}

// ---------------------------------------------------------------- Private documents
function formatBytes(n) {
  return n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(2)} MB` : `${(n / 1024).toFixed(1)} KB`;
}

async function loadDocuments() {
  const body = $('documents-body');
  skeletonRows(body, 4, 3);
  try {
    const data = await api('GET', '/documents');
    body.replaceChildren();
    if (!data.documents.length) body.append(emptyRow(4, 'file', 'Bucket documents đang trống.'));
    for (const d of data.documents) {
      const name = el('span', 'file-name');
      name.append(icon('file'), document.createTextNode(d.name));
      const nameTd = el('td');
      nameTd.append(name);
      const btn = el('button', 'btn btn-small');
      btn.type = 'button';
      btn.append(icon('download'), document.createTextNode('Tải về'));
      btn.onclick = () => downloadDocument(d.name);
      const act = el('td', 'actions');
      act.append(btn);
      const tr = el('tr');
      tr.append(nameTd, el('td', 'num', formatBytes(d.bytes)), el('td', 'nowrap', new Date(d.modified).toLocaleString('vi-VN')), act);
      body.append(tr);
    }
  } catch (e) {
    body.replaceChildren(emptyRow(4, 'lock', e.status === 403 ? `403 – ${e.message}` : e.message, 'st-warn'));
  }
}

async function downloadDocument(name) {
  try {
    const res = await api('GET', `/documents/${encodeURIComponent(name)}`, undefined, { raw: true });
    if (!res.ok) throw Object.assign(new Error(`HTTP ${res.status}`), { status: res.status });
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement('a'), { href: url, download: name });
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) { showError(e); }
}

// ---------------------------------------------------------------- Operations
async function loadSystemSummary() {
  try {
    const res = await fetch('/api/status', { cache: 'no-store' });
    const data = await res.json();
    const { up, total } = data.summary;
    countUp($('ops-stat-up'), up, el('small', '', ` / ${total}`));
    $('ops-stat-up').className = `stat-value ${up === total ? 'status-up' : 'status-down'}`;
  } catch (e) {
    $('ops-stat-up').textContent = '–';
  }
}

async function loadAlerts() {
  const body = $('alerts-body');
  skeletonRows(body, 7, 3);
  loadSystemSummary();
  try {
    const data = await api('GET', '/alerts');
    body.replaceChildren();
    $('ops-firing').textContent = `${data.firing} đang firing`;
    $('ops-firing').className = data.firing ? 'badge badge-red' : 'badge badge-green';
    countUp($('ops-stat-firing'), data.firing);
    $('ops-stat-firing').className = `stat-value ${data.firing ? 'status-down' : 'status-up'}`;
    countUp($('ops-stat-resolved'), data.alerts.filter((a) => a.status !== 'firing').length);
    if (!data.alerts.length) body.append(emptyRow(7, 'bell', 'Chưa có cảnh báo nào.'));
    const fmt = (v) => (v ? new Date(v).toLocaleString('vi-VN') : '');
    for (const a of data.alerts) {
      const firing = a.status === 'firing';
      const st = el('td');
      st.append(el('span', `badge ${firing ? 'badge-err' : 'badge-ok'}`, a.status));
      const sev = el('td');
      sev.append(el('span', `badge ${a.severity === 'critical' ? 'badge-err' : a.severity === 'warning' ? 'badge-warn' : 'badge-gray'}`, a.severity || '–'));
      const tr = el('tr');
      tr.append(st, el('td', 'mono', a.alertname), sev, el('td', 'mono small', a.target || ''), el('td', '', a.summary || ''),
        el('td', 'nowrap small', fmt(a.starts_at)), el('td', 'nowrap small', fmt(a.ends_at)));
      body.append(tr);
    }
  } catch (e) {
    $('ops-firing').textContent = '';
    for (const id of ['ops-stat-firing', 'ops-stat-resolved']) $(id).textContent = '–';
    body.replaceChildren(emptyRow(7, 'lock', e.status === 403 ? `403 – ${e.message}` : e.message, 'st-warn'));
  }
}
$('btn-reload-alerts').onclick = loadAlerts;

function renderOpsLinks() {
  const host = location.hostname;
  const links = [
    ['chart', 'Grafana – Tổng quan', `http://${host}:3000/d/overview-523h0008-523h0025`],
    ['log', 'Grafana – Logs (Loki)', `http://${host}:3000/d/logs-523h0008-523h0025`],
    ['box', 'Grafana – Container', `http://${host}:3000/d/containers-523h0008-523h0025`],
    ['activity', 'Grafana – API RED', `http://${host}:3000/d/api-red-523h0008-523h0025`],
    ['bell', 'Prometheus – Alerts', `http://${host}:9090/alerts`],
    ['bell', 'Alertmanager', `http://${host}:9093/`],
  ];
  $('ops-links').replaceChildren();
  for (const [ic, title, url] of links) {
    const card = el('a', 'card');
    card.href = url;
    card.target = '_blank';
    card.rel = 'noopener';
    const h = el('h3');
    h.append(icon(ic), document.createTextNode(title), icon('external', 'ic ext'));
    card.append(h, el('p', 'mono muted', url));
    $('ops-links').append(card);
  }
}

// ---------------------------------------------------------------- Tab
// The underline under the selected tab slides (transform only) instead of jumping
function moveIndicator(tab) {
  const bar = $('tab-indicator');
  if (!bar || !tab) return;
  bar.style.transform = `translateX(${tab.offsetLeft}px) scaleX(${tab.offsetWidth})`;
}
addEventListener('resize', () => moveIndicator(document.querySelector('.tab.active')));
const loaders = { profile: loadProfile, students: loadStudents, documents: loadDocuments, ops: loadAlerts };
for (const tab of document.querySelectorAll('.tab')) {
  tab.addEventListener('click', () => {
    for (const t of document.querySelectorAll('.tab')) {
      t.classList.toggle('active', t === tab);
      t.setAttribute('aria-selected', String(t === tab));
    }
    for (const p of document.querySelectorAll('.panel')) {
      const on = p.dataset.panel === tab.dataset.tab;
      show(p, on);
      p.classList.toggle('fade-enter', on);
    }
    moveIndicator(tab);
    location.hash = tab.dataset.tab;
    loaders[tab.dataset.tab]().catch(showError);
  });
}

// ---------------------------------------------------------------- Khởi động
$('btn-login').onclick = login;
$('btn-logout').onclick = logout;

(async function init() {
  try {
    await handleCallback();
  } catch (e) {
    showLoginError(`Đăng nhập không thành công: ${e.message}`);
  }
  if (!(await accessToken().catch(() => null))) {
    show($('view-login'));
    return;
  }
  show($('view-app'));
  show($('portal-nav'));
  moveIndicator(document.querySelector('.tab.active'));
  show($('nav-user'));
  show($('btn-logout'));
  renderOpsLinks();
  try { await loadProfile(); } catch (e) { showError(e); }
  setInterval(tickExpiry, 1000);
  tickExpiry();
  const start = location.hash.slice(1);
  if (start && start !== 'profile' && loaders[start]) document.querySelector(`.tab[data-tab="${start}"]`).click();
})();
