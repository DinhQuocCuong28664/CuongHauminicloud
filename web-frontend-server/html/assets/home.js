// Trang chủ: bảng trạng thái trực tiếp (/api/status), minh hoạ round robin (X-Served-By) và tô màu sơ đồ kiến trúc.
// Chuyển động chỉ đánh dấu điều quan trọng: các dòng hiện lần lượt một lần, dòng đổi trạng thái thì nháy,
// số liệu chính đếm lên một lần, mũi tên trên sơ đồ tự vẽ khi cuộn tới.
'use strict';

(function () {
  const $ = (id) => document.getElementById(id);
  const { countUp, flash, onReveal, reduceMotion } = window.mmc;
  const REFRESH_MS = 5000;
  const LB_MS = 10000;

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  const small = (text) => el('small', '', text);

  function statusBadge(up) {
    const b = el('span', `badge ${up ? 'badge-ok' : 'badge-err'}`);
    b.append(el('span', 'dot'), document.createTextNode(up ? 'Hoạt động' : 'Lỗi'));
    return b;
  }

  function serviceRow(s) {
    const up = s.status === 'up';
    const row = el('article', `svc ${up ? 'up' : 'down'}`);
    row.dataset.svc = s.id;
    const role = el('div', 'svc-role', s.group === 'core' ? `${s.role_no}. ${s.role}` : s.role);
    const name = el('div', 'svc-name');
    name.append(el('span', '', /^web\d$/.test(s.id) ? `${s.tech} · ${s.id}` : s.tech), statusBadge(up));
    const meta = el('div', 'svc-meta');
    const left = el('span', 'mono', s.container);
    left.title = s.container;
    meta.append(left, el('span', 'nowrap', s.latency_ms == null ? '–' : `${Math.round(s.latency_ms)} ms`));
    row.title = s.detail ? `Kiểm tra: ${s.detail}` : '';
    row.append(role, name, meta);
    return row;
  }

  function skeleton(board, n) {
    board.replaceChildren();
    for (let i = 0; i < n; i++) {
      const row = el('div', 'svc skel');
      row.append(el('span', 'bar skeleton'), el('span', 'bar skeleton'));
      board.append(row);
    }
  }

  function setState(kind, text) {
    const b = $('board-state');
    b.className = `badge ${kind}`;
    b.replaceChildren(el('span', 'dot'), document.createTextNode(text));
  }

  function paintArchitecture(services, changed) {
    const byId = new Map(services.map((s) => [s.id, s.status]));
    for (const node of document.querySelectorAll('.arch [data-svc]')) {
      const st = byId.get(node.dataset.svc);
      node.classList.toggle('down', st === 'down');
    }
    for (const id of changed) {
      const node = document.querySelector(`.arch [data-svc="${id}"]`);
      if (node && !reduceMotion()) {
        node.animate([{ opacity: 0.3 }, { opacity: 1 }], { duration: 300, iterations: 2, easing: 'ease-out' });
      }
    }
  }

  // Vẽ bảng; lần tải đầu các dòng hiện lần lượt, các lần sau chỉ dòng đổi trạng thái mới nháy
  const previous = new Map();
  function renderBoard(board, services, firstLoad) {
    const rows = services.map(serviceRow);
    board.replaceChildren(...rows);
    rows.forEach((row, i) => {
      const id = row.dataset.svc;
      const before = previous.get(id);
      if (firstLoad) {
        row.classList.add('enter');
        row.style.setProperty('--i', i);
      } else if (before && before !== (row.classList.contains('up') ? 'up' : 'down')) {
        flash(row);
      }
    });
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
      const core = data.services.filter((s) => s.group === 'core').sort((a, b) => a.role_no - b.role_no);
      const extra = data.services.filter((s) => s.group !== 'core');
      const changed = data.services.filter((s) => previous.has(s.id) && previous.get(s.id) !== s.status).map((s) => s.id);
      renderBoard($('board-core'), core, firstLoad);
      renderBoard($('board-extra'), extra, firstLoad);
      paintArchitecture(data.services, changed);
      data.services.forEach((s) => previous.set(s.id, s.status));

      const { up, total, extra_up: eu, extra_total: et } = data.summary;
      countUp($('st-up'), up, small(` / ${total}`));
      countUp($('st-extra'), eu, small(` / ${et}`));
      $('st-up').className = `stat-value ${up === total ? 'status-up' : 'status-down'}`;
      $('st-up-foot').textContent = up === total ? 'tất cả container chính đều hoạt động'
        : `đang lỗi: ${core.filter((s) => s.status !== 'up').map((s) => s.id).join(', ')}`;
      $('st-latency').replaceChildren(document.createTextNode(String(Math.round(ms))), small(' ms'));

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

  // ---------------------------------------------------------------- minh hoạ round robin
  // Mỗi phản hồi hiện ngay khi về, nên thấy rõ thứ tự web1, web2, web1...
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
        row.append(el('span', 'mono', name), track, el('span', 'num', '0/6'));
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

  // ---------------------------------------------------------------- kiến trúc: mũi tên tự vẽ một lần khi hiện ra
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
  onReveal($('can-bang-tai'), runLb);
  setInterval(() => { if (!document.hidden) runLb(); }, LB_MS);
})();
