#!/usr/bin/env python3
"""auto_login.py — Mở Chrome và tự động đăng nhập vào 7 tab MyMiniCloud
Đọc thông tin tài khoản và mật khẩu trực tiếp từ CuongHauminicloud/.env
"""
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ENV_FILE = HERE / ".env"

env = {}
if ENV_FILE.exists():
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")

def get(k, default=""):
    return env.get(k, default)

PROXY_PORT = get("PROXY_PORT", "80")
AUTH_PORT = get("AUTH_PORT", "8081")
MINIO_CONSOLE_PORT = get("MINIO_CONSOLE_PORT", "9001")
GRAFANA_PORT = get("GRAFANA_PORT", "3000")
PROM_PORT = get("PROM_PORT", "9090")

# DEMO_TARGET=ec2 (set by scripts/ec2/open_tabs.py) opens the same 7 tabs on the EC2 instance:
# HTTPS through the proxy (Let's Encrypt on <dashed-ip>.sslip.io) and the admin tools on their own ports,
# which the security group opens only to the IP that ran launch.sh. Local runs keep the localhost URLs.
TARGET = os.environ.get("DEMO_TARGET", "local")
if TARGET == "ec2":
    _inst = {}
    for _ln in (HERE / "scripts" / "ec2" / "instance.env").read_text(encoding="utf-8").splitlines():
        if "=" in _ln:
            _k, _v = _ln.split("=", 1)
            _inst[_k.strip()] = _v.strip()
    EC2_IP = _inst["PUBLIC_IP"]
    EC2_DOMAIN = EC2_IP.replace(".", "-") + ".sslip.io"
    WEB = f"https://{EC2_DOMAIN}"
    KC_URL = f"{WEB}/auth/admin/"
    MINIO_URL = f"http://{EC2_IP}:{MINIO_CONSOLE_PORT}/login"
    GF_URL = f"http://{EC2_IP}:{GRAFANA_PORT}/login"
    PROM_URL = f"http://{EC2_IP}:{PROM_PORT}/targets"
else:
    WEB = f"http://localhost:{PROXY_PORT}"
    KC_URL = f"http://localhost:{AUTH_PORT}/auth/admin/"
    MINIO_URL = f"http://localhost:{MINIO_CONSOLE_PORT}/login"
    GF_URL = f"http://localhost:{GRAFANA_PORT}/login"
    PROM_URL = f"http://localhost:{PROM_PORT}/targets"

KC_ADMIN = get("KC_ADMIN", "admin")
KC_ADMIN_PW = get("KC_ADMIN_PASSWORD", "admin")
SV_PASSWORD = get("SV_PASSWORD", "change-me")
MINIO_USER = get("MINIO_ROOT_USER", "minioadmin")
MINIO_PW = get("MINIO_ROOT_PASSWORD", "minioadmin")
GF_USER = get("GF_ADMIN_USER", "admin")
GF_PW = get("GF_ADMIN_PASSWORD", "admin")

# Chrome runs as its own detached process with a debugging port, so it stays open after this script
# (and the menu) exits. Playwright only attaches over CDP to log in, then disconnects.
# Usage: auto_login.py [open|focus|close]   (default: open)
import subprocess
from chrome_raise import raise_window
import urllib.request

# The EC2 Chrome is a separate window (own port and profile) so it can stay open next to the local one
CDP_PORT = int(get("DEMO_CHROME_PORT_EC2", "9223")) if TARGET == "ec2" else int(get("DEMO_CHROME_PORT", "9222"))
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"
PROFILE_DIR = HERE / (".demo-chrome-profile-ec2" if TARGET == "ec2" else ".demo-chrome-profile")
MODE = sys.argv[1] if len(sys.argv) > 1 else "open"


def chrome_alive():
    try:
        urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=1.5).read()
        return True
    except Exception:
        return False


def find_chrome():
    for c in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")):
        if os.path.isfile(c):
            return c
    return None


def start_chrome():
    exe = find_chrome()
    if not exe:
        print("[LỖI] Không tìm thấy Google Chrome.")
        sys.exit(1)
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [exe, f"--remote-debugging-port={CDP_PORT}", f"--user-data-dir={PROFILE_DIR}",
         "--no-first-run", "--no-default-browser-check", "--start-maximized", "about:blank"],
        creationflags=flags, close_fds=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(40):
        if chrome_alive():
            return
        time.sleep(0.5)
    print("[LỖI] Chrome không mở được cổng điều khiển.")
    sys.exit(1)


print("=" * 70)
print("     TỰ ĐỘNG MỞ TRÌNH DUYỆT & ĐĂNG NHẬP 7 TAB MYMINICLOUD")
print("=" * 70)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("[LỖI] Chưa cài playwright. Hãy chạy: pip install playwright")
    sys.exit(1)

if MODE in ("focus", "close"):
    if not chrome_alive():
        print(">>> Chrome demo chưa mở.")
        sys.exit(2)
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        if MODE == "close":
            browser.new_browser_cdp_session().send("Browser.close")
            print(">>> Đã đóng Chrome demo.")
        else:
            pages = browser.contexts[0].pages if browser.contexts else []
            if pages:
                pages[0].bring_to_front(); raise_window(pages[0])
            print(">>> Đã đưa Chrome demo lên trước (các tab giữ nguyên, không đăng nhập lại).")
    sys.exit(0)

def keycloak_login(page, user, password, ok_selector, attempts=3, ok_state="visible"):
    """Fill the Keycloak login form and wait for ok_selector; retry because the form can be submitted too early."""
    for _ in range(attempts):
        try:
            page.wait_for_selector("#username", timeout=15000)
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            page.fill("#username", user)
            page.fill("#password", password)
            page.click("#kc-login")
            page.wait_for_selector(ok_selector, state=ok_state, timeout=10000)
            return True
        except Exception:
            continue
    return False


if MODE == "goto":
    # Show a URL in the demo Chrome without a new login: reuse the tab on the same origin+path when there is one
    url = sys.argv[2]
    if not chrome_alive():
        sys.exit(2)
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]
        from urllib.parse import urlsplit
        key = url.split("?")[0].rstrip("/")
        target_origin = "{0.scheme}://{0.netloc}".format(urlsplit(url))
        proxy_origin = "{0.scheme}://{0.netloc}".format(urlsplit(WEB))
        live = [x for x in ctx.pages if x.url.startswith("http")]
        pg = next((x for x in live if x.url.split("?")[0].rstrip("/") == key), None)
        if pg is None and target_origin != proxy_origin:
            # Grafana, MinIO, Prometheus: reuse the tab that is already open for that tool (Tab 5, 6, 7)
            pg = next((x for x in live if x.url.startswith(target_origin)), None)
        if pg is None and target_origin == proxy_origin and urlsplit(url).path.startswith("/api/"):
            # API pages share one tab so repeated demo keys do not pile up new tabs
            pg = next((x for x in live if x.url.startswith(proxy_origin + "/api/")), None)
        if pg is None:
            pg = ctx.new_page()
        pg.bring_to_front(); raise_window(pg)
        pg.goto(url, timeout=20000)
        print("  tab:", "tái sử dụng" if pg in live else "mở mới")
    sys.exit(0)

if MODE == "portal":
    # Switch the Portal tab to another user without typing: auto_login.py portal sv01|sv02
    target = sys.argv[2] if len(sys.argv) > 2 else "sv01"
    if not chrome_alive():
        print(">>> Chrome demo chưa mở. Hãy bấm phím 8 ở menu trước.")
        sys.exit(2)
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]
        pg = next((x for x in ctx.pages if "/portal/" in x.url and "/auth/" not in x.url), None)
        if pg is None:
            pg = ctx.new_page()
            pg.goto(f"{WEB}/portal/", timeout=15000)
        pg.bring_to_front(); raise_window(pg)
        pg.wait_for_selector("#btn-login:visible, #btn-logout:visible", timeout=15000)
        if pg.locator("#btn-logout").is_visible():
            print(">>> Đang đăng xuất tài khoản hiện tại...")
            pg.click("#btn-logout")
            pg.wait_for_selector("#btn-login:visible", timeout=15000)
        pg.click("#btn-login")
        pg.wait_for_selector("#username:visible, #view-app:not([hidden])", timeout=15000)
        if pg.locator("#username").is_visible():
            ok = keycloak_login(pg, target, SV_PASSWORD, "#view-app:not([hidden])")
        else:
            ok = True   # Keycloak SSO session still open: signed in without the form
        if not ok:
            print(f"[LỖI] Chưa đăng nhập được {target}.")
            sys.exit(1)
        print(f">>> Đã đăng nhập Portal bằng {target}.")
        pg.click('button[data-tab="students"]')
        if target == "sv02":
            # viewer: try a write so the 403 shows on screen (nothing is saved)
            pg.fill("#s-student-id", "SV999")
            pg.fill("#s-fullname", "Demo Viewer")
            pg.click("#btn-save-student")
            print(">>> Đã thử Thêm sinh viên bằng sv02: Portal hiện lỗi 403 (không lưu gì).")
        else:
            print(">>> sv01 (editor): mở tab Sinh viên, có thể Thêm/Sửa/Xoá. Script không tự ghi dữ liệu.")
    sys.exit(0)

if not chrome_alive():
    print(">>> Đang khởi chạy Google Chrome (chạy độc lập, không đóng khi thoát menu)...")
    start_chrome()

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(CDP_URL)
    context = browser.contexts[0]
    # The blank start tab(s) are closed once the demo tabs are open
    blank_pages = [pg for pg in context.pages if pg.url == "about:blank"]

    # -------------------------------------------------------------
    # TAB 1: Trang chủ Dashboard & 14 Status Cards
    # -------------------------------------------------------------
    print("[1/7] Đang mở Tab 1: Trang chủ Dashboard...")
    page_home = context.new_page()
    try:
        page_home.goto(f"{WEB}/", timeout=15000)
        print("  -> OK: Trang chủ đã sẵn sàng.")
    except Exception as e:
        print(f"  -> Bỏ qua hoặc chưa bật container: {e}")

    # -------------------------------------------------------------
    # TAB 2: MyMiniCloud Portal (SPA) & Đăng nhập OIDC PKCE
    # -------------------------------------------------------------
    print("[2/7] Đang mở Tab 2: MyMiniCloud Portal & Đăng nhập sv01...")
    page_portal = context.new_page()
    try:
        page_portal.bring_to_front()   # a hidden (background) tab can stall the login form scripts
        page_portal.goto(f"{WEB}/portal/", timeout=15000)
        page_portal.wait_for_selector("#btn-login:visible, #view-app:not([hidden])", timeout=15000)
        btn_login = page_portal.locator("#btn-login")
        if btn_login.count() and btn_login.is_visible():
            btn_login.click()
            if keycloak_login(page_portal, "sv01", SV_PASSWORD, "#view-app:not([hidden])"):
                print("  -> OK: Đã đăng nhập Portal thành công với tài khoản sv01 (editor).")
            else:
                print("  -> Lưu ý Portal: chưa đăng nhập được, hãy đăng nhập tay trên giao diện.")
        else:
            print("  -> OK: Portal đã đăng nhập sẵn.")
    except Exception as e:
        print(f"  -> Lưu ý Portal (có thể đăng nhập tay trên giao diện): {e}")

    # -------------------------------------------------------------
    # TAB 3: Blog cá nhân (6 bài viết)
    # -------------------------------------------------------------
    print("[3/7] Đang mở Tab 3: Blog cá nhân...")
    page_blog = context.new_page()
    try:
        page_blog.goto(f"{WEB}/blog/", timeout=15000)
        print("  -> OK: Blog cá nhân đã sẵn sàng.")
    except Exception as e:
        print(f"  -> Bỏ qua: {e}")

    # -------------------------------------------------------------
    # TAB 4: Keycloak Admin Console
    # -------------------------------------------------------------
    print("[4/7] Đang mở Tab 4: Keycloak Admin Console & Đăng nhập...")
    page_kc = context.new_page()
    try:
        page_kc.bring_to_front()
        page_kc.goto(KC_URL, timeout=20000)
        # The admin console always redirects to the login form first; the form is gone once logged in
        if keycloak_login(page_kc, KC_ADMIN, KC_ADMIN_PW, "#username", ok_state="hidden"):
            print(f"  -> OK: Đã đăng nhập Keycloak Admin thành công ({KC_ADMIN}).")
        else:
            print("  -> Lưu ý Keycloak: chưa đăng nhập được, hãy đăng nhập tay trên giao diện.")
    except Exception as e:
        print(f"  -> Lưu ý Keycloak (có thể đăng nhập tay): {e}")

    # -------------------------------------------------------------
    # TAB 5: MinIO Object Storage Console
    # -------------------------------------------------------------
    print("[5/7] Đang mở Tab 5: MinIO Console (cổng 9001) & Đăng nhập...")
    page_minio = context.new_page()
    try:
        page_minio.bring_to_front()
        page_minio.goto(MINIO_URL, timeout=15000)
        time.sleep(1)
        access_key = page_minio.locator('#accessKey, input[name="accessKey"], input[placeholder="Username"]').first
        if access_key.count() and access_key.is_visible():
            access_key.fill(MINIO_USER)
            page_minio.locator('#secretKey, input[name="secretKey"], input[type="password"]').first.fill(MINIO_PW)
            page_minio.locator('#do-login, button[type="submit"]').first.click()
            time.sleep(2)
            print("  -> OK: Đã đăng nhập MinIO Console thành công.")
        else:
            print("  -> OK: MinIO đã đăng nhập sẵn.")
    except Exception as e:
        print(f"  -> Lưu ý MinIO (có thể đăng nhập tay): {e}")

    # -------------------------------------------------------------
    # TAB 6: Grafana Dashboards
    # -------------------------------------------------------------
    print("[6/7] Đang mở Tab 6: Grafana Dashboards (cổng 3000) & Đăng nhập...")
    page_gf = context.new_page()
    try:
        page_gf.bring_to_front()
        page_gf.goto(GF_URL, timeout=15000)
        time.sleep(1)
        gf_user_inp = page_gf.locator('input[name="user"]')
        if gf_user_inp.count() and gf_user_inp.is_visible():
            gf_user_inp.fill(GF_USER)
            page_gf.locator('input[name="password"]').fill(GF_PW)
            page_gf.locator('button[type="submit"]').click()
            time.sleep(2)
            print("  -> OK: Đã đăng nhập Grafana thành công.")
        else:
            print("  -> OK: Grafana đã đăng nhập sẵn.")
    except Exception as e:
        print(f"  -> Lưu ý Grafana: {e}")

    # -------------------------------------------------------------
    # TAB 7: Prometheus Targets (no login needed)
    # -------------------------------------------------------------
    print("[7/7] Đang mở Tab 7: Prometheus Targets (cổng 9090)...")
    page_prom = context.new_page()
    try:
        page_prom.goto(PROM_URL, timeout=15000)
        print("  -> OK: Prometheus Targets đã sẵn sàng.")
    except Exception as e:
        print(f"  -> Lưu ý Prometheus: {e}")

    for pg in blank_pages:
        try:
            pg.close()
        except Exception:
            pass
    # Focus Tab 1 (home page) to start presenting
    try:
        page_home.bring_to_front(); raise_window(page_home)
    except Exception:
        pass

    print("")
    print("=" * 70)
    print(" [THÀNH CÔNG] TOÀN BỘ CÁC TAB ĐÃ MỞ & TỰ ĐỘNG ĐĂNG NHẬP HOÀN TẤT!")
    print(" Chrome chạy độc lập: thoát menu hoặc script này KHÔNG đóng các tab.")
    print(" Muốn vào lại: bấm phím 8 ở menu rồi chọn F (đưa Chrome lên, không đăng nhập lại).")
    print("=" * 70)
    # No browser.close(): leaving the "with" block only disconnects Playwright, Chrome keeps running.
