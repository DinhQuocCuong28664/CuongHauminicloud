#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""demo_browser.py - drive the demo Chrome (started by DEMO.bat key 8) so the browser shows what a demo key does.

Usage: python scripts/demo_browser.py <action>
  a01   Portal logout -> Keycloak login page (PKCE URL visible) -> login sv01
  a03   Portal > Sinh vien: add SV990, edit it, delete it (visible in the table)
  a04   Portal: reload profile (new avatar) and open the documents tab
  ops   Portal > Van hanh: reload the alerts table
  a08   Fire 40 parallel requests from the browser and show the 200 / 429 counts on the page
Exit code 2 when the demo Chrome is not running.
"""
import os
import subprocess
from chrome_raise import raise_window
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent.parent
ENV = {}
for _l in (HERE / ".env").read_text(encoding="utf-8").splitlines():
    _l = _l.strip()
    if _l and not _l.startswith("#") and "=" in _l:
        _k, _v = _l.split("=", 1)
        ENV[_k.strip()] = _v.strip().strip('"').strip("'")

PORT = ENV.get("PROXY_PORT", "80")
if os.environ.get("DEMO_TARGET") == "ec2":
    # Same actions against the EC2 instance, in the EC2 Chrome window (port 9223) opened by scripts/ec2/open_tabs.py
    _inst = dict(l.split("=", 1) for l in (HERE / "scripts" / "ec2" / "instance.env").read_text(encoding="utf-8").splitlines() if "=" in l)
    _ip = _inst["PUBLIC_IP"].strip()
    BASE = f"https://{_ip.replace('.', '-')}.sslip.io"
    MINIO_BASE = f"http://{_ip}:{ENV.get('MINIO_CONSOLE_PORT', '9001')}"
    CDP = f"http://127.0.0.1:{ENV.get('DEMO_CHROME_PORT_EC2', '9223')}"
else:
    BASE = "http://localhost" if PORT == "80" else f"http://localhost:{PORT}"
    MINIO_BASE = f"http://localhost:{ENV.get('MINIO_CONSOLE_PORT', '9001')}"
    CDP = f"http://127.0.0.1:{ENV.get('DEMO_CHROME_PORT', '9222')}"
SV_PASSWORD = ENV["SV_PASSWORD"]


def chrome_alive():
    try:
        urllib.request.urlopen(f"{CDP}/json/version", timeout=1.5).read()
        return True
    except Exception:
        return False


def portal_page(ctx):
    pg = next((x for x in ctx.pages if x.url.startswith(f"{BASE}/portal") and "/auth/" not in x.url), None)
    if pg is None:
        pg = ctx.new_page()
        pg.goto(f"{BASE}/portal/", timeout=15000)
    pg.bring_to_front(); raise_window(pg)
    return pg


def ensure_user(pg, user):
    """Make sure the Portal tab is signed in as <user>; reuse the key 10/11 login when it is not."""
    try:
        pg.wait_for_selector("#nav-user:visible, #btn-login:visible", timeout=8000)
        if pg.locator("#nav-user").is_visible() and user in pg.inner_text("#nav-user"):
            return pg
    except Exception:
        pass
    subprocess.run([sys.executable, "scripts/auto_login.py", "portal", user], cwd=HERE, capture_output=True)
    pg.wait_for_selector("#nav-user:visible", timeout=20000)
    return pg


# DEMO_PACE slows every demo step so the audience can follow (1 = fast, 2 = default, 3 = very slow).
# Set it in .env (DEMO_PACE=3) or in the environment; no redeploy is needed, these scripts run on this machine.
PACE = float(os.environ.get("DEMO_PACE") or ENV.get("DEMO_PACE") or "2")


def pause(sec=1.5):
    time.sleep(sec * PACE)


def typ(pg, selector, text):
    """Type into a field character by character so viewers see it being filled in."""
    loc = pg.locator(selector)
    loc.fill("")
    loc.press_sequentially(text, delay=int(45 * PACE))


def a01(pg):
    if pg.locator("#btn-logout").is_visible():
        pg.click("#btn-logout")
    pg.wait_for_selector("#btn-login:visible", timeout=15000)
    pg.click("#btn-login")
    pg.wait_for_selector("#username:visible", timeout=15000)
    print("  >>> Trình duyệt đang ở trang đăng nhập Keycloak; thanh địa chỉ có code_challenge_method=S256 (PKCE).")
    pause(4)
    typ(pg, "#username", "sv01")
    pause(1)
    typ(pg, "#password", SV_PASSWORD)
    pause(1)
    pg.click("#kc-login")
    pg.wait_for_selector("#view-app:not([hidden])", timeout=15000)
    print("  >>> Đã quay về Portal với token (không có client secret nào trong trình duyệt).")
    pause(3)


def a03(pg):
    ensure_user(pg, "sv01")
    pg.click('button[data-tab="students"]')
    pg.wait_for_selector("#students-body tr", timeout=10000)
    pause(2)
    row = pg.locator('#students-body tr:has-text("SV990")')
    for attempt in (1, 2, 3):
        typ(pg, "#s-student-id", "SV990")
        typ(pg, "#s-fullname", "Demo CRUD")
        typ(pg, "#s-major", "Cloud")
        pause(1.5)
        pg.click("#btn-save-student")
        try:
            row.wait_for(timeout=6000)
            break
        except Exception:
            toast = pg.inner_text("#toast").strip() if pg.locator("#toast").count() else ""
            print(f"  >>> Lần {attempt}: chưa thấy dòng SV990 (thông báo Portal: '{toast}'), thử lại sau 4 giây...")
            if attempt == 3:
                raise
            pause(4)   # the gateway rate limit (A08) or a slow reload can reject the first save
    print("  >>> THÊM: dòng SV990 xuất hiện trong bảng.")
    pause(3)
    row.locator('button:has-text("Sửa")').click()
    pause(2)
    typ(pg, "#s-major", "DevOps")
    pause(1.5)
    pg.click("#btn-save-student")
    pg.locator('#students-body tr:has-text("SV990"):has-text("DevOps")').wait_for(timeout=8000)
    print("  >>> SỬA: ngành của SV990 đổi sang DevOps.")
    pause(3)
    pg.locator('#students-body tr:has-text("SV990") button:has-text("Xoá")').click()
    pg.wait_for_selector("#confirm-dialog[open]", timeout=5000)
    print("  >>> XOÁ: hộp xác nhận hiện ra.")
    pause(2.5)
    pg.click("#confirm-ok")
    pg.wait_for_selector('#students-body tr:has-text("SV990")', state="detached", timeout=8000)
    print("  >>> Dòng SV990 đã biến mất (dữ liệu trở lại như cũ).")
    pause(3)


def a04(pg):
    ensure_user(pg, "sv01")
    pg.reload(wait_until="networkidle")
    pg.wait_for_selector("#nav-user:visible", timeout=15000)
    pg.click('button[data-tab="profile"]')
    print("  >>> Hồ sơ: ảnh đại diện lấy từ MinIO (bucket profile-pics) qua /media/.")
    pause(3)
    pg.click('button[data-tab="documents"]')
    pg.wait_for_selector("#documents-body tr", timeout=10000)
    print("  >>> Tài liệu: danh sách PDF private (chỉ editor tải được).")
    pause(3)


def ops(pg):
    ensure_user(pg, "sv01")
    pg.click('button[data-tab="ops"]')
    pause(1)
    pg.click("#btn-reload-alerts")
    pause(2)
    print("  >>> Portal > Vận hành: bảng cảnh báo đã tải lại.")


def a08(ctx):
    pg = next((x for x in ctx.pages if x.url.rstrip("/") == f"{BASE}/api/hello"), None) or ctx.new_page()
    pg.goto(f"{BASE}/api/hello", timeout=15000)
    pg.bring_to_front(); raise_window(pg)
    res = pg.evaluate("""async () => {
      const codes = await Promise.all(Array.from({length: 40}, () => fetch('/api/hello').then(r => r.status).catch(() => 0)));
      const c = {}; for (const s of codes) c[s] = (c[s] || 0) + 1;
      const html = '<div style="font:20px Arial;padding:40px"><h1>Rate limit: 40 request cùng lúc từ trình duyệt</h1>' +
        Object.entries(c).sort().map(([k, v]) => '<p><b style="font-size:48px;color:' + (k == 429 ? '#c0392b' : '#27ae60') +
        '">' + v + '</b> request trả HTTP <b>' + k + '</b>' + (k == 429 ? ' (Too Many Requests: bị giới hạn 10 request/giây)' : ' (được phục vụ)') + '</p>').join('') + '</div>';
      document.body.innerHTML = html;
      return c;
    }""")
    print(f"  >>> Trình duyệt tự bắn 40 request: {res}")


def minio(ctx):
    """Open the db-backups bucket in the MinIO console, signing in first when needed.
    Opening /browser/<bucket> while signed out makes the console redirect to a relative 'login' again and again
    (.../login/login/login...), so always go through /login."""
    base = MINIO_BASE
    pg = next((x for x in ctx.pages if x.url.startswith(base)), None) or ctx.new_page()
    pg.bring_to_front(); raise_window(pg)
    pg.goto(f"{base}/login", timeout=15000)
    pg.wait_for_timeout(1200)
    user = pg.locator('#accessKey, input[name="accessKey"], input[placeholder="Username"]').first
    if user.count() and user.is_visible():
        user.fill(ENV.get("MINIO_ROOT_USER", "minioadmin"))
        pg.locator('#secretKey, input[name="secretKey"], input[type="password"]').first.fill(
            ENV.get("MINIO_ROOT_PASSWORD", "minioadmin"))
        pg.locator('#do-login, button[type="submit"]').first.click()
        pg.wait_for_timeout(2500)
    pg.goto(f"{base}/browser/db-backups", timeout=15000)
    print("  >>> MinIO console: bucket db-backups, thấy các file .sql.gz mới sao lưu.")


ACTIONS = {"a01": a01, "a03": a03, "a04": a04, "ops": ops}

if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action not in ACTIONS and action not in ("a08", "minio"):
        print("Usage: python scripts/demo_browser.py a01|a03|a04|ops|a08|minio")
        sys.exit(1)
    if not chrome_alive():
        print("  >>> Chrome demo chưa mở (bấm phím 8 trước) - bỏ qua phần trình duyệt.")
        sys.exit(2)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        try:
            if action == "a08":
                a08(ctx)
            elif action == "minio":
                minio(ctx)
            else:
                ACTIONS[action](portal_page(ctx))
        except Exception as e:
            print(f"  >>> Lưu ý phần trình duyệt: {type(e).__name__}: {str(e).splitlines()[0]}")
            sys.exit(1)
