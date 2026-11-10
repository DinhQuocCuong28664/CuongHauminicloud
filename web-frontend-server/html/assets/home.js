// Home page: service cards fed by /api/status (with a client-side check history), the resource bar
// (host CPU/RAM, traffic, alerts), the round-robin demo (X-Served-By) and architecture colouring.
// Motion only marks what matters: cards appear once in sequence, a card flashes when its status changes,
// and the diagram arrows draw themselves when scrolled into view.
'use strict';

(function () {
  const $ = (id) => document.getElementById(id);
  const { flash, onReveal, reduceMotion } = window.mmc;
  const REFRESH_MS = 5000;
  const LB_MS = 10000;
  const HISTORY = 30;
  const HISTORY_KEY = 'mmc-status-history';

  // Service logo: colour SVG as <img>, single-colour SVG as a CSS mask so it follows the theme, else initials
  const LOGOS = {
    proxy: 'nginx', web1: 'nginx', web2: 'nginx', app: 'flask:mono', db: 'mariadb', auth: 'keycloak',
    storage: 'minio:mono', monitoring: 'prometheus', grafana: 'grafana', 'node-exporter': 'prometheus',
    alertmanager: 'alertmanager', loki: 'loki', alloy: 'alloy',
  };
  const INITIALS = { dns: 'DNS', cadvisor: 'cA' };

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function logoTile(id) {
    const tile = el('span', 'logo-tile');
    const spec = LOGOS[id];
    if (!spec) {
      tile.classList.add('text');
      tile.textContent = INITIALS[id] || id.slice(0, 2);
      return tile;
    }
    const [name, kind] = spec.split(':');
    if (kind === 'mono') {
      tile.append(el('span', `mono-logo ${name}`));
    } else {
      const img = el('img');
      img.src = `/assets/logos/${name}.svg`;
      img.alt = '';
      tile.append(img);
    }
    return tile;
  }

  // ---------------------------------------------------------------- check history (kept per browser tab)
  let history = {};
  try { history = JSON.parse(sessionStorage.getItem(HISTORY_KEY) || '{}') || {}; } catch (e) { history = {}; }
  function record(services) {
    for (const s of services) {
      const h = (history[s.id] = history[s.id] || []);
      h.push(s.status === 'up' ? 1 : 0);
      if (h.length > HISTORY) h.splice(0, h.length - HISTORY);
    }
    try { sessionStorage.setItem(HISTORY_KEY, JSON.stringify(history)); } catch (e) { /* not persisted */ }
  }

  function serviceCard(s) {
    const up = s.status === 'up';
    const card = el('article', `svc ${up ? 'up' : 'down'}`);
    card.dataset.svc = s.id;
    card.title = s.detail ? `Kiểm tra: ${s.detail}` : '';

    const head = el('div', 'svc-head');
    const names = el('div');
    const title = /^web\d$/.test(s.id) ? `${s.role} ${s.id.slice(3)}` : s.role;
    names.append(el('h3', '', title), el('div', 'svc-sub', s.group === 'core' ? `Loại ${s.role_no}, ${s.tech}` : s.tech));
    head.append(logoTile(s.id), names);

    const h = history[s.id] || [];
    const availability = h.length ? Math.round((100 * h.reduce((a, b) => a + b, 0)) / h.length) : null;
    const stats = el('div', 'svc-stats');
    const stat = (value, label) => { const d = el('div'); d.append(el('b', '', value), el('span', '', label)); return d; };
    stats.append(
      stat(s.latency_ms == null ? '–' : `${Math.round(s.latency_ms)} ms`, 'độ trễ'),
      stat(availability == null ? '–' : `${availability}%`, 'sẵn sàng'));

    const ticks = el('div', 'ticks');
    ticks.setAttribute('aria-hidden', 'true');
    for (let i = 0; i < HISTORY - h.length; i++) ticks.append(el('i'));
    for (const v of h) ticks.append(el('i', v ? 'up' : 'down'));

    const foot = el('div', 'svc-foot');
    const name = el('span', 'mono', s.container);
    name.title = s.container;
    foot.append(name, el('span', 'svc-tag', up ? 'Đang chạy' : 'Lỗi'));

    card.append(head, stats, ticks, foot);
    return card;
  }

  function skeleton(board, n) {
    board.replaceChildren();
    for (let i = 0; i < n; i++) {
      const card = el('div', 'svc skel');
      card.append(el('span', 'bar skeleton'), el('span', 'bar skeleton'));
      board.append(card);
    }
  }

  function setState(kind, text) {
    const b = $('board-state');
    b.className = `badge ${kind}`;
    b.replaceChildren(el('span', 'dot'), document.createTextNode(text));
  }

  function meter(id, fraction, warnAt, badAt) {
    const bar = $(id);
    const v = fraction == null ? 0 : Math.max(0, Math.min(1, fraction));
    bar.querySelector('span').style.setProperty('--v', v);
    bar.classList.toggle('warn', warnAt != null && v >= warnAt && v < badAt);
    bar.classList.toggle('bad', badAt != null && v >= badAt);
  }

  function paintArchitecture(services, changed) {
    const byId = new Map(services.map((s) => [s.id, s.status]));
    for (const node of document.querySelectorAll('.arch [data-svc]')) {
      node.classList.toggle('down', byId.get(node.dataset.svc) === 'down');
    }
    for (const id of changed) {
      const node = document.querySelector(`.arch [data-svc="${id}"]`);
      if (node && !reduceMotion()) {
        node.animate([{ opacity: 0.3 }, { opacity: 1 }], { duration: 300, iterations: 2, easing: 'ease-out' });
      }
    }
  }

  // Render a board; on the first load cards enter one after another, later only changed cards flash
  const previous = new Map();
  function renderBoard(board, services, firstLoad) {
    const cards = services.map(serviceCard);
    board.replaceChildren(...cards);
    cards.forEach((card, i) => {
      const before = previous.get(card.dataset.svc);
      if (firstLoad) {
        card.classList.add('enter');
        card.style.setProperty('--i', i);
      } else if (before && before !== (card.classList.contains('up') ? 'up' : 'down')) {
        flash(card);
      }
    });
  }

  function renderResources(data, ms) {
    const host = data.host || {};
    const fmt = (v, digits = 0) => (v == null ? '–' : Number(v).toFixed(digits));
    $('res-host-spec').textContent = host.cpus == null ? 'không đọc được Prometheus'
      : `${fmt(host.cpus)} vCPU, ${fmt(host.mem_total_gb, 1)} GB RAM`;
    $('res-cpu').textContent = `CPU ${fmt(host.cpu_pct)}%`;
    $('res-mem').textContent = `RAM ${fmt(host.mem_pct)}%`;
    meter('res-mem-bar', host.mem_pct == null ? null : host.mem_pct / 100, 0.75, 0.9);

    const { up, total, extra_up: eu, extra_total: et } = data.summary;
    $('res-containers').textContent = host.containers == null ? 'trong cloud-net' : `${fmt(host.containers)} container`;
    $('st-up').textContent = `${up}/${total} chạy`;
    $('st-extra').textContent = `nâng cao ${eu}/${et}`;
    meter('res-up-bar', total ? up / total : 0);
    if (up === total) $('res-up-bar').classList.remove('bad'); else $('res-up-bar').classList.add('bad');

    $('res-traffic').textContent = `${fmt(host.web_req_per_min)} req/phút`;
    $('st-latency').textContent = `API ${Math.round(ms)} ms`;
    meter('res-traffic-bar', host.web_req_per_min == null ? null : host.web_req_per_min / 600);

    const alerts = data.alerts;
    $('res-alerts').textContent = alerts == null ? 'không đọc được' : `${alerts.length} đang kích hoạt`;
    $('res-alerts').title = alerts && alerts.length ? alerts.join(', ') : '';
    const down = data.services.filter((s) => s.group === 'core' && s.status !== 'up').map((s) => s.id);
    $('st-up-foot').textContent = down.length ? `lỗi: ${down.join(', ')}` : `${total}/${total} server ổn`;
    meter('res-alert-bar', alerts == null ? null : 1);
    $('res-alert-bar').classList.toggle('bad', !!(alerts && alerts.length));
  }

  let timer = null;
  let loading = false;
  let firstLoad = true;
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
      record(data.services);
      const core = data.services.filter((s) => s.group === 'core').sort((a, b) => a.role_no - b.role_no);
      const extra = data.services.filter((s) => s.group !== 'core');
      const changed = data.services.filter((s) => previous.has(s.id) && previous.get(s.id) !== s.status).map((s) => s.id);
      renderBoard($('board-core'), core, firstLoad);
      renderBoard($('board-extra'), extra, firstLoad);
      paintArchitecture(data.services, changed);
      data.services.forEach((s) => previous.set(s.id, s.status));
      renderResources(data, ms);

      const down = data.services.filter((s) => s.status !== 'up').length;
      setState(down ? 'badge-err' : 'badge-ok', down ? `${down} thành phần đang lỗi` : 'Hệ thống hoạt động bình thường');
      $('board-time').textContent = `Kiểm tra lúc ${new Date(data.checked_at).toLocaleTimeString('vi-VN')}`;
      firstLoad = false;
    } catch (e) {
      if (e.code === 404) {
        setState('badge-gray', 'Không có API');
        $('board-time').textContent = 'Bảng trạng thái cần đi qua gateway (cổng 80/443); trang đang mở trực tiếp từ web server.';
        const note = el('div', 'board-note empty');
        note.append(el('strong', '', 'Trang đang mở thẳng từ web server, không qua gateway.'),
          el('p', 'muted small', 'Web server chỉ phục vụ trang tĩnh. Mở trang qua gateway (cổng 80) để xem trạng thái các server.'));
        $('board-core').replaceChildren(note);
        $('board-extra').replaceChildren();
        $('board-extra').previousElementSibling.hidden = true;
        for (const id of ['st-up', 'st-extra', 'st-latency', 'res-cpu', 'res-mem', 'res-traffic', 'res-alerts']) $(id).textContent = '–';
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

  // ---------------------------------------------------------------- shortcut links to the admin ports
  const https = location.protocol === 'https:';
  for (const a of document.querySelectorAll('.link[data-port]')) {
    a.href = `http://${location.hostname}:${a.dataset.port}${a.dataset.path || '/'}`;
    a.target = '_blank';
    a.rel = 'noopener';
  }
  if (https) $('links-note').hidden = false;

  // ---------------------------------------------------------------- round robin demo
  // Each response appears as soon as it arrives, so the alternation web1, web2, web1... is visible.
  let lbRunning = false;
  async function runLb() {
    if (lbRunning) return;
    lbRunning = true;
    $('lb-run').classList.add('busy');
    const strip = $('lb-strip');
    strip.replaceChildren();
    const counts = {};
    const bars = $('lb-bars');
    if (!bars.children.length) {
      for (const name of ['web1', 'web2']) {
        const row = el('div', `lb-bar ${name}`);
        const track = el('div', 'track');
        track.append(el('div', 'fill'));
        row.append(el('span', '', name), track, el('span', 'num', '0/6'));
        row.dataset.name = name;
        bars.append(row);
      }
    }
    const paintBars = (n) => {
      for (const row of bars.children) {
        const c = counts[row.dataset.name] || 0;
        row.querySelector('.fill').style.transform = `scaleX(${c / 6})`;
        row.querySelector('.num').textContent = `${c}/${n}`;
      }
    };
    paintBars(0);
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
      paintBars(i + 1);
      if (!reduceMotion()) await new Promise((r) => setTimeout(r, 120));
    }
    const only = Object.keys(counts).filter((k) => /^web\d$/.test(k));
    $('lb-note').textContent = only.length === 2
      ? 'Hai server luân phiên trả lời: gateway đang cân bằng tải.'
      : only.length === 1
        ? `Chỉ ${only[0]} trả lời: server còn lại đang dừng hoặc trang mở thẳng từ một web server, gateway tự chuyển hết request sang ${only[0]}.`
        : 'Không nhận được header X-Served-By.';
    $('lb-run').classList.remove('busy');
    lbRunning = false;
  }

  // ---------------------------------------------------------------- architecture: arrows draw once when visible
  const arch = document.querySelector('.arch');
  if (arch && !reduceMotion()) {
    arch.classList.add('will-draw');
    onReveal(arch, () => requestAnimationFrame(() => arch.classList.add('drawn')));
  }

  skeleton($('board-core'), 10);
  skeleton($('board-extra'), 5);
  $('board-refresh').addEventListener('click', loadStatus);
  $('lb-run').addEventListener('click', runLb);
  timer = setInterval(() => { if (!document.hidden) loadStatus(); }, REFRESH_MS);
  loadStatus();
  setTimeout(runLb, 800);
  setInterval(() => { if (!document.hidden) runLb(); }, LB_MS);
})();
