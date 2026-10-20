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
  const tr = document.createElement('tr');
  const cls = status >= 500 ? 'st-err' : status >= 400 ? 'st-warn' : 'st-ok';
  tr.innerHTML = `<td>${new Date().toLocaleTimeString('vi-VN')}</td><td class="mono"></td>
    <td class="${cls}">${status}</td><td>${ms.toFixed(0)} ms</td><td class="mono small"></td>`;
  tr.children[1].textContent = `${method} /api${path}`;
  tr.children[4].textContent = requestId || '';
  const body = $('calls-body');
  body.prepend(tr);
  while (body.children.length > 12) body.lastChild.remove();
}

function toast(text, kind = 'ok') {
  const el = $('toast');
  el.textContent = text;
  el.className = `msg msg-${kind}`;
  show(el);
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => show(el, false), 5000);
}
function showError(e) {
  toast(e.status === 403 ? `Bị từ chối (403): ${e.message}` : `Lỗi: ${e.message}`, 'error');
}
function showLoginError(text) { const el = $('login-error'); el.textContent = text; show(el); }

// ---------------------------------------------------------------- Hồ sơ
let me = null;

async function loadProfile() {
  me = await api('GET', '/me');
  $('nav-user').textContent = me.username;
  // Tên tiếng Việt: họ đứng trước tên (claim name của Keycloak ghép theo kiểu tên trước họ)
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
  $('students-note').textContent = me.roles.includes('editor')
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
}

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

// ---------------------------------------------------------------- Sinh viên (CRUD)
async function loadStudents() {
  const data = await api('GET', '/students');
  const body = $('students-body');
  body.innerHTML = '';
  for (const s of data.students) {
    const tr = document.createElement('tr');
    for (const v of [s.id, s.student_id, s.fullname, s.dob || '', s.major || '']) {
      const td = document.createElement('td');
      td.textContent = v;
      tr.append(td);
    }
    const td = document.createElement('td');
    td.className = 'actions';
    const edit = Object.assign(document.createElement('button'), { className: 'btn btn-small', textContent: 'Sửa' });
    const del = Object.assign(document.createElement('button'), { className: 'btn btn-small btn-danger', textContent: 'Xoá' });
    edit.onclick = () => startEdit(s);
    del.onclick = () => deleteStudent(s);
    td.append(edit, ' ', del);
    tr.append(td);
    body.append(tr);
  }
}

function startEdit(s) {
  $('s-id').value = s.id;
  $('s-student-id').value = s.student_id;
  $('s-fullname').value = s.fullname;
  $('s-dob').value = s.dob || '';
  $('s-major').value = s.major || '';
  $('btn-save-student').textContent = `Lưu #${s.id}`;
  show($('btn-cancel-edit'));
}
function resetForm() {
  $('form-student').reset();
  $('s-id').value = '';
  $('btn-save-student').textContent = 'Thêm';
  show($('btn-cancel-edit'), false);
}

$('form-student').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const id = $('s-id').value;
  const body = {
    student_id: $('s-student-id').value.trim(), fullname: $('s-fullname').value.trim(),
    dob: $('s-dob').value || null, major: $('s-major').value.trim(),
  };
  try {
    const s = id ? await api('PUT', `/students/${id}`, body) : await api('POST', '/students', body);
    toast(id ? `Đã cập nhật ${s.student_id}` : `Đã thêm ${s.student_id} (id ${s.id})`);
    resetForm();
    await loadStudents();
  } catch (e) { showError(e); }
});
$('btn-cancel-edit').onclick = resetForm;
$('btn-reload-students').onclick = () => loadStudents().catch(showError);

async function deleteStudent(s) {
  if (!confirm(`Xoá sinh viên ${s.student_id} – ${s.fullname}?`)) return;
  try {
    await api('DELETE', `/students/${s.id}`);
    toast(`Đã xoá ${s.student_id}`);
    await loadStudents();
  } catch (e) { showError(e); }
}

// ---------------------------------------------------------------- Tài liệu private
async function loadDocuments() {
  const body = $('documents-body');
  body.innerHTML = '';
  try {
    const data = await api('GET', '/documents');
    for (const d of data.documents) {
      const tr = document.createElement('tr');
      tr.innerHTML = '<td class="mono"></td><td></td><td></td><td></td>';
      tr.children[0].textContent = d.name;
      tr.children[1].textContent = `${(d.bytes / 1024 / 1024).toFixed(2)} MB`;
      tr.children[2].textContent = new Date(d.modified).toLocaleString('vi-VN');
      const btn = Object.assign(document.createElement('button'), { className: 'btn btn-small', textContent: 'Tải về' });
      btn.onclick = () => downloadDocument(d.name);
      tr.children[3].append(btn);
      body.append(tr);
    }
  } catch (e) {
    body.innerHTML = '<tr><td colspan="4" class="st-warn"></td></tr>';
    body.querySelector('td').textContent = e.status === 403 ? `403 – ${e.message}` : e.message;
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

// ---------------------------------------------------------------- Vận hành
async function loadAlerts() {
  const body = $('alerts-body');
  body.innerHTML = '';
  try {
    const data = await api('GET', '/alerts');
    $('ops-firing').textContent = `${data.firing} đang firing`;
    $('ops-firing').className = data.firing ? 'badge badge-red' : 'badge badge-green';
    if (!data.alerts.length) body.innerHTML = '<tr><td colspan="7" class="muted">Chưa có cảnh báo nào.</td></tr>';
    for (const a of data.alerts) {
      const tr = document.createElement('tr');
      const fmt = (v) => (v ? new Date(v).toLocaleString('vi-VN') : '');
      for (const [v, cls] of [[a.status, a.status === 'firing' ? 'st-err' : 'st-ok'], [a.alertname], [a.severity],
        [a.target], [a.summary], [fmt(a.starts_at)], [fmt(a.ends_at)]]) {
        const td = document.createElement('td');
        td.textContent = v || '';
        if (cls) td.className = cls;
        tr.append(td);
      }
      body.append(tr);
    }
  } catch (e) {
    $('ops-firing').textContent = '';
    body.innerHTML = '<tr><td colspan="7" class="st-warn"></td></tr>';
    body.querySelector('td').textContent = e.status === 403 ? `403 – ${e.message}` : e.message;
  }
}
$('btn-reload-alerts').onclick = loadAlerts;

function renderOpsLinks() {
  const host = location.hostname;
  const links = [
    ['Grafana – Tổng quan', `http://${host}:3000/d/overview-523h0008-523h0025`],
    ['Grafana – Logs (Loki)', `http://${host}:3000/d/logs-523h0008-523h0025`],
    ['Grafana – Container', `http://${host}:3000/d/containers-523h0008-523h0025`],
    ['Grafana – API RED', `http://${host}:3000/d/api-red-523h0008-523h0025`],
    ['Prometheus – Alerts', `http://${host}:9090/alerts`],
    ['Alertmanager', `http://${host}:9093/`],
  ];
  $('ops-links').innerHTML = '';
  for (const [title, url] of links) {
    const card = document.createElement('a');
    card.className = 'card link-card';
    card.href = url;
    card.target = '_blank';
    card.rel = 'noopener';
    card.innerHTML = '<h3></h3><p class="mono small"></p>';
    card.querySelector('h3').textContent = title;
    card.querySelector('p').textContent = url;
    $('ops-links').append(card);
  }
}

// ---------------------------------------------------------------- Tab
const loaders = { profile: loadProfile, students: loadStudents, documents: loadDocuments, ops: loadAlerts };
for (const tab of document.querySelectorAll('.tab')) {
  tab.addEventListener('click', () => {
    for (const t of document.querySelectorAll('.tab')) t.classList.toggle('active', t === tab);
    for (const p of document.querySelectorAll('.panel')) show(p, p.dataset.panel === tab.dataset.tab);
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
  show($('nav-user'));
  show($('btn-logout'));
  renderOpsLinks();
  try { await loadProfile(); } catch (e) { showError(e); }
  setInterval(tickExpiry, 1000);
  tickExpiry();
  const start = location.hash.slice(1);
  if (start && start !== 'profile' && loaders[start]) document.querySelector(`.tab[data-tab="${start}"]`).click();
})();
