// Site shell shared by every page: theme toggle, header menus, current page, tool links, blog table of contents,
// plus small motion helpers (count-up, flash, shake, reveal) used by home.js and portal.js.
'use strict';

(function () {
  const root = document.documentElement;
  const ICONS = '/assets/icons.svg';
  const reduceMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

  function icon(name, cls = 'ic') {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', cls);
    svg.setAttribute('aria-hidden', 'true');
    const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttribute('href', `${ICONS}#${name}`);
    svg.append(use);
    return svg;
  }

  // ---------------------------------------------------------------- motion helpers
  // Number runs from 0 to its value once (400 ms, ease-out); suffix nodes such as "<small> / 10</small>" are kept.
  function countUp(el, value, suffixNode) {
    const done = () => el.replaceChildren(document.createTextNode(String(value)), ...(suffixNode ? [suffixNode] : []));
    if (reduceMotion() || !Number.isFinite(value) || value === 0 || el.dataset.counted) { done(); return; }
    el.dataset.counted = '1';
    const t0 = performance.now();
    const step = (t) => {
      const k = Math.min(1, (t - t0) / 400);
      const eased = 1 - Math.pow(1 - k, 3);
      el.replaceChildren(document.createTextNode(String(Math.round(value * eased))), ...(suffixNode ? [suffixNode] : []));
      if (k < 1) requestAnimationFrame(step); else done();
    };
    requestAnimationFrame(step);
  }
  // One-off highlight that marks "this just changed"
  function flash(el) {
    el.classList.remove('flash');
    void el.offsetWidth;          // restart the animation
    el.classList.add('flash');
    setTimeout(() => el.classList.remove('flash'), 950);
  }
  // Short horizontal shake for an input or button that was rejected
  function shake(el) {
    if (!el) return;
    el.classList.remove('shake');
    void el.offsetWidth;
    el.classList.add('shake');
    el.addEventListener('animationend', () => el.classList.remove('shake'), { once: true });
  }
  // Run fn once, when el first scrolls into view
  function onReveal(el, fn) {
    if (!el) return;
    if (!('IntersectionObserver' in window)) { fn(); return; }
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) { io.disconnect(); fn(); }
    }, { threshold: 0.25 });
    io.observe(el);
  }
  window.mmc = { icon, countUp, flash, shake, onReveal, reduceMotion };
  window.mmcIcon = icon;

  // ---------------------------------------------------------------- light / dark
  function currentTheme() {
    if (root.dataset.theme) return root.dataset.theme;
    return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  const toggle = document.getElementById('theme-toggle');
  if (toggle) {
    const label = () => toggle.setAttribute('aria-label',
      currentTheme() === 'dark' ? 'Chuyển sang giao diện sáng' : 'Chuyển sang giao diện tối');
    label();
    toggle.addEventListener('click', () => {
      const next = currentTheme() === 'dark' ? 'light' : 'dark';
      const apply = () => { root.dataset.theme = next; label(); };
      // Cross-fade the whole page when the browser supports view transitions
      if (document.startViewTransition && !reduceMotion()) document.startViewTransition(apply); else apply();
      try { localStorage.setItem('mmc-theme', next); } catch (e) { /* not persisted */ }
    });
  }

  // ---------------------------------------------------------------- header: mobile menu and tools dropdown
  const header = document.getElementById('site-header');
  const menuBtn = document.getElementById('menu-toggle');
  const tools = document.getElementById('tools-menu');
  const setMenu = (open) => {
    if (!header) return;
    header.classList.toggle('nav-open', open);
    if (menuBtn) menuBtn.setAttribute('aria-expanded', String(open));
  };
  if (menuBtn) menuBtn.addEventListener('click', () => setMenu(!header.classList.contains('nav-open')));
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    setMenu(false);
    if (tools && tools.open) { tools.open = false; tools.querySelector('summary').focus(); }
  });
  document.addEventListener('click', (e) => {
    if (tools && tools.open && !tools.contains(e.target)) tools.open = false;
    if (header && header.classList.contains('nav-open') && !header.contains(e.target)) setMenu(false);
  });

  // Current page in the main navigation
  const section = location.pathname.startsWith('/blog') ? 'blog'
    : location.pathname.startsWith('/portal') ? 'portal' : 'home';
  const current = document.querySelector(`.main-nav a[data-nav="${section}"]`);
  if (current) current.setAttribute('aria-current', 'page');

  // Tool links. The admin ports are only open to the team's IP on EC2, so over HTTPS only Keycloak is listed.
  const toolLinks = document.getElementById('tool-links');
  if (toolLinks) {
    const host = location.hostname;
    const https = location.protocol === 'https:';
    const list = [
      ['Grafana', `http://${host}:3000/`, !https],
      ['Prometheus', `http://${host}:9090/targets`, !https],
      ['Alertmanager', `http://${host}:9093/`, !https],
      ['MinIO Console', `http://${host}:9001/`, !https],
      ['Keycloak Admin', `${location.origin}/auth/admin/`, true],
    ];
    for (const [name, url, visible] of list) {
      if (!visible) continue;
      const a = document.createElement('a');
      a.href = url;
      a.target = '_blank';
      a.rel = 'noopener';
      a.append(document.createTextNode(name), icon('external', 'ic ext'));
      toolLinks.append(a);
    }
    if (https) {
      const p = document.createElement('p');
      p.className = 'menu-note';
      p.textContent = 'Grafana, Prometheus, MinIO chỉ mở cho IP của nhóm.';
      toolLinks.append(p);
    }
  }

  // ---------------------------------------------------------------- blog: table of contents and reading time
  const toc = document.getElementById('toc-list');
  const article = document.querySelector('article.post');
  if (toc && article) {
    const heads = [...article.querySelectorAll('h2')];
    heads.forEach((h, i) => {
      if (!h.id) h.id = `muc-${i + 1}`;
      const li = document.createElement('li');
      const a = document.createElement('a');
      a.href = `#${h.id}`;
      a.textContent = h.textContent;
      li.append(a);
      toc.append(li);
    });
    if (!heads.length) toc.closest('.toc').hidden = true;
    if ('IntersectionObserver' in window && heads.length) {
      const links = new Map([...toc.querySelectorAll('a')].map((a) => [a.hash.slice(1), a]));
      const io = new IntersectionObserver((entries) => {
        for (const en of entries) {
          if (!en.isIntersecting) continue;
          links.forEach((a) => a.classList.remove('active'));
          const a = links.get(en.target.id);
          if (a) a.classList.add('active');
        }
      }, { rootMargin: '0px 0px -70% 0px' });
      heads.forEach((h) => io.observe(h));
    }
  }
  const rt = document.getElementById('reading-time');
  if (rt && article) {
    const words = article.textContent.trim().split(/\s+/).length;
    rt.textContent = `${Math.max(1, Math.round(words / 220))} phút đọc`;
  }
})();
