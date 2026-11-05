// Home page: live status board (/api/status), round-robin demo (X-Served-By) and architecture colouring.
'use strict';

(function () {
  const $ = (id) => document.getElementById(id);
  const icon = (name, cls) => window.mmcIcon(name, cls);
  const REFRESH_MS = 5000;
  const LB_MS = 10000;

  const ICON_BY_ID = {
    proxy: 'proxy', web1: 'web', web2: 'web', app: 'app', db: 'db', auth: 'key', storage: 'bucket', dns: 'dns',
    monitoring: 'activity', grafana: 'chart', 'node-exporter': 'cpu', cadvisor: 'box', alertmanager: 'bell',
    loki: 'log', alloy: 'log',
  };

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function statusBadge(up) {
    const b = el('span', `badge ${up ? 'badge-ok' : 'badge-err'}`);
    const dot = el('span', `dot${up ? '' : ' pulse'}`);
    b.append(dot, document.createTextNode(up ? 'UP' : 'DOWN'));
    return b;
  }

  function serviceCard(s) {
    const up = s.status === 'up';
    const card = el('article', `svc ${up ? 'up' : 'down'}`);
    card.dataset.svc = s.id;
    const ic = el('div', 'svc-icon');
    ic.append(icon(ICON_BY_ID[s.id] || 'box', 'ic'));
    const role = el('div', 'svc-role', s.group === 'core' ? `${s.role_no}. ${s.role}` : s.role);
    const name = el('div', 'svc-name');
    name.append(el('span', '', /^web\d$/.test(s.id) ? `${s.tech} · ${s.id}` : s.tech), statusBadge(up));
    const meta = el('div', 'svc-meta');
    const left = el('span', 'mono', s.container);
    left.title = s.container;
    const right = el('span', 'nowrap', s.latency_ms == null ? '–' : `${Math.round(s.latency_ms)} ms`);
    meta.append(left, right);
    card.title = s.detail ? `Kiểm tra: ${s.detail}` : '';
    card.append(ic, role, name, meta);
    return card;
  }

  function skeleton(board, n) {
    board.replaceChildren();
    for (let i = 0; i < n; i++) {
      const c = el('div', 'svc');
      c.append(el('div', 'svc-icon skeleton'), el('div', 'svc-role skeleton', 'loading'), el('div', 'svc-name skeleton', 'loading'));
      board.append(c);
    }
  }

  function setState(kind, text) {
    const b = $('board-state');
    b.className = `badge ${kind}`;
    b.replaceChildren(el('span', `dot${kind === 'badge-ok' ? ' pulse' : ''}`), document.createTextNode(text));
  }

  function paintArchitecture(services) {
    const byId = new Map(services.map((s) => [s.id, s.status]));
    for (const node of document.querySelectorAll('.arch [data-svc]')) {
      const st = byId.get(node.dataset.svc);
      node.classList.toggle('down', st === 'down');
      node.classList.toggle('up', st === 'up' && node.classList.contains('a-node'));
    }
  }

  let timer = null;
  let loading = false;
  async function loadStatus() {
    if (loading) return;
    loading = true;
    const t0 = performance.now();
    try {
      const res = await fetch('/api/status', { cache: 'no-store', headers: { Accept: 'application/json' } });
      const ms = performance.now() - t0;
      if (res.status === 404) throw Object.assign(new Error('no-gateway'), { code: 404 });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const core = data.services.filter((s) => s.group === 'core').sort((a, b) => a.role_no - b.role_no);
      const extra = data.services.filter((s) => s.group !== 'core');
      $('board-core').replaceChildren(...core.map(serviceCard));
      $('board-extra').replaceChildren(...extra.map(serviceCard));
      paintArchitecture(data.services);

      const { up, total, extra_up: eu, extra_total: et } = data.summary;
      $('st-up').replaceChildren(document.createTextNode(String(up)), el('small', '', ` / ${total}`));
      $('st-up-foot').textContent = up === total ? 'tất cả container chính đều UP'
        : `lỗi: ${core.filter((s) => s.status !== 'up').map((s) => s.id).join(', ')}`;
      $('st-up').className = `stat-value ${up === total ? 'status-up' : 'status-down'}`;
      $('st-extra').replaceChildren(document.createTextNode(String(eu)), el('small', '', ` / ${et}`));
      $('st-latency').replaceChildren(document.createTextNode(String(Math.round(ms))), el('small', '', ' ms'));

      const down = data.services.filter((s) => s.status !== 'up').length;
      setState(down ? 'badge-warn' : 'badge-ok', down ? `${down} thành phần đang lỗi` : 'Hệ thống hoạt động bình thường');
      $('board-time').textContent = `Kiểm tra lúc ${new Date(data.checked_at).toLocaleTimeString('vi-VN')}`;
    } catch (e) {
      if (e.code === 404) {
        setState('badge-gray', 'Không có API');
        $('board-time').textContent = 'Bảng trạng thái cần đi qua gateway (cổng 80/443); trang đang mở trực tiếp từ web server.';
        const note = el('div', 'card empty board-note');
        note.append(icon('proxy', 'ic'), el('strong', '', 'Trang đang mở thẳng từ web server, không qua gateway.'),
          el('p', 'muted small', 'Web server chỉ phục vụ trang tĩnh. Mở trang qua gateway (cổng 80) để xem trạng thái các server.'));
        $('board-core').replaceChildren(note);
        $('board-extra').replaceChildren();
        $('board-extra').previousElementSibling.hidden = true;
        for (const id of ['st-up', 'st-extra', 'st-latency']) $(id).textContent = '–';
        $('st-up-foot').textContent = 'mở qua gateway để xem';
        clearInterval(timer);
      } else {
        setState('badge-err', 'Mất kết nối tới API');
        $('board-time').textContent = `Lần thử lúc ${new Date().toLocaleTimeString('vi-VN')}: ${e.message}`;
      }
    } finally {
      loading = false;
    }
  }

  // ---------------------------------------------------------------- round robin demo
  let lbRunning = false;
  async function runLb() {
    if (lbRunning) return;
    lbRunning = true;
    const strip = $('lb-strip');
    strip.replaceChildren();
    const counts = {};
    for (let i = 0; i < 6; i++) {
      let name;
      try {
        const res = await fetch(`/?lb=${Date.now()}-${i}`, { method: 'HEAD', cache: 'no-store' });
        name = res.headers.get('X-Served-By') || `HTTP ${res.status}`;
      } catch (e) {
        name = 'lỗi';
      }
      counts[name] = (counts[name] || 0) + 1;
      const hit = el('span', `lb-hit ${/^web\d$/.test(name) ? name : 'err'}`);
      hit.append(el('span', 'muted', `#${i + 1}`), document.createTextNode(name));
      strip.append(hit);
    }
    const bars = $('lb-bars');
    bars.replaceChildren();
    for (const name of ['web1', 'web2']) {
      const n = counts[name] || 0;
      const row = el('div', `lb-bar ${name}`);
      const track = el('div', 'track');
      const fill = el('div', 'fill');
      fill.style.width = `${(n / 6) * 100}%`;
      track.append(fill);
      row.append(el('span', 'mono', name), track, el('span', 'num', `${n}/6`));
      bars.append(row);
    }
    const only = Object.keys(counts).filter((k) => /^web\d$/.test(k));
    $('lb-note').textContent = only.length === 2
      ? 'Hai server luân phiên trả lời: gateway đang cân bằng tải.'
      : only.length === 1
        ? `Chỉ ${only[0]} trả lời: server còn lại đang dừng hoặc trang mở thẳng từ một web server, gateway tự chuyển hết request sang ${only[0]}.`
        : 'Không nhận được header X-Served-By.';
    lbRunning = false;
  }

  skeleton($('board-core'), 10);
  skeleton($('board-extra'), 5);
  $('board-refresh').addEventListener('click', loadStatus);
  $('lb-run').addEventListener('click', runLb);
  timer = setInterval(() => { if (!document.hidden) loadStatus(); }, REFRESH_MS);
  loadStatus();
  runLb();
  setInterval(() => { if (!document.hidden) runLb(); }, LB_MS);
})();
