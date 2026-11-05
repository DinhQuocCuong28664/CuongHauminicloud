// Console shell shared by every page: theme toggle, mobile sidebar, active link, tool links, blog table of contents.
'use strict';

(function () {
  const root = document.documentElement;
  const ICONS = '/assets/icons.svg';

  function icon(name, cls = 'ic') {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', cls);
    svg.setAttribute('aria-hidden', 'true');
    const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttribute('href', `${ICONS}#${name}`);
    svg.append(use);
    return svg;
  }
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
      root.dataset.theme = next;
      try { localStorage.setItem('mmc-theme', next); } catch (e) { /* not persisted */ }
      label();
    });
  }

  // ---------------------------------------------------------------- mobile sidebar
  const menu = document.getElementById('menu-toggle');
  if (menu) {
    const setOpen = (open) => {
      document.body.classList.toggle('nav-open', open);
      menu.setAttribute('aria-expanded', String(open));
    };
    menu.addEventListener('click', () => setOpen(!document.body.classList.contains('nav-open')));
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') setOpen(false); });
    document.addEventListener('click', (e) => {
      if (document.body.classList.contains('nav-open') && !e.target.closest('.sidebar, #menu-toggle')) setOpen(false);
    });
    document.querySelectorAll('.sidebar .side-link').forEach((a) => a.addEventListener('click', () => setOpen(false)));
  }

  // ---------------------------------------------------------------- active section in the sidebar
  const section = location.pathname.startsWith('/blog') ? 'blog'
    : location.pathname.startsWith('/portal') ? 'portal' : 'home';
  const active = document.querySelector(`.sidebar a[data-nav="${section}"]`);
  if (active) active.setAttribute('aria-current', 'page');

  // ---------------------------------------------------------------- tool links
  // The admin ports are only open to the team's IP on EC2, so over HTTPS only Keycloak (behind the gateway) is listed.
  const tools = document.getElementById('tool-links');
  if (tools) {
    const host = location.hostname;
    const https = location.protocol === 'https:';
    const list = [
      ['chart', 'Grafana', `http://${host}:3000/`, !https],
      ['activity', 'Prometheus', `http://${host}:9090/targets`, !https],
      ['bell', 'Alertmanager', `http://${host}:9093/`, !https],
      ['bucket', 'MinIO Console', `http://${host}:9001/`, !https],
      ['key', 'Keycloak Admin', `${location.origin}/auth/admin/`, true],
    ];
    for (const [ic, name, url, visible] of list) {
      if (!visible) continue;
      const a = document.createElement('a');
      a.className = 'side-link';
      a.href = url;
      a.target = '_blank';
      a.rel = 'noopener';
      a.append(icon(ic), document.createTextNode(name), icon('external', 'ic ext'));
      tools.append(a);
    }
    if (https) {
      const p = document.createElement('p');
      p.className = 'side-note';
      p.textContent = 'Grafana, Prometheus, MinIO chỉ mở cho IP của nhóm.';
      tools.append(p);
    }
  }

  // ---------------------------------------------------------------- blog: table of contents from <h2>
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

  // ---------------------------------------------------------------- reading time for blog posts
  const rt = document.getElementById('reading-time');
  if (rt && article) {
    const words = article.textContent.trim().split(/\s+/).length;
    rt.textContent = `${Math.max(1, Math.round(words / 220))} phút đọc`;
  }
})();
