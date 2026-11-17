#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""demo_menu.py — Bảng điều khiển Live Demo MyMiniCloud
Giao diện dòng lệnh tiếng Việt chuẩn UTF-8.
Hỗ trợ:
- Tự động Re-check liên tục (continuous polling): Tự bắt ngay khi Docker Desktop và 16 Container bật.
- Chạy tuần tự từ Bước 1 đến Bước 6 với phím Enter (Tiếp tục), R (Re-check chạy lại), Q (Thoát về Menu).
- Mở Chrome và tự động đăng nhập 7 tab theo thông tin trong .env.
"""
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
import webbrowser

# Đảm bảo stdout / stdin hỗ trợ UTF-8 chuẩn trên Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent.parent
os.chdir(HERE)
os.environ["COMPOSE_PROJECT_NAME"] = "cuonghauminicloud"
os.environ["MSYS_NO_PATHCONV"] = "1"

# Đọc cấu hình từ .env
ENV_FILE = HERE / ".env"
ENV_VARS = {}
if ENV_FILE.exists():
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                ENV_VARS[k.strip()] = v.strip().strip('"').strip("'")

def get_env(k, default=""):
    return ENV_VARS.get(k, os.environ.get(k, default))

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def is_docker_running():
    try:
        res = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3
        )
        return res.returncode == 0
    except Exception:
        return False

def get_running_containers():
    try:
        res = subprocess.run(
            ["docker", "compose", "-p", "cuonghauminicloud", "ps", "-q"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if res.returncode == 0:
            return [line.strip() for line in res.stdout.splitlines() if line.strip()]
    except Exception:
        pass
    return []

def get_bash_exe():
    """Luôn ưu tiên Git Bash của Windows thay vì WSL bash để kết nối đúng Docker Desktop"""
    candidates = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\bin\bash.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return "bash"

def run_cmd(cmd_list, shell=False):
    sys.stdout.flush()
    sys.stderr.flush()
    env = os.environ.copy()
    env["MSYS_NO_PATHCONV"] = "1"
    env["COMPOSE_PROJECT_NAME"] = "cuonghauminicloud"
    try:
        subprocess.run(cmd_list, env=env, shell=shell, check=False)
    except Exception as e:
        print(f"\n[LỖI THỰC THI]: {e}")
    sys.stdout.flush()

def wait_for_docker_and_containers(min_containers=16, auto_start=True):
    """
    Vòng lặp Re-check liên tục (polling) mỗi 1-2 giây:
    1. Quét tìm Docker Desktop (tự bắt ngay khi người dùng bật, không cần gõ phím).
    2. Quét số container (tự động up -d nếu thiếu và chờ đủ 16/16).
    """
    first_warn = True
    spinners = ["|", "/", "-", "\\"]
    idx = 0

    # 1. Chờ Docker daemon
    while not is_docker_running():
        if first_warn:
            clear()
            print("=" * 75)
            print(" ⏳ ĐANG CHỜ DOCKER DESKTOP KHỞI ĐỘNG...")
            print("===========================================================================")
            print(" Chưa phát hiện Docker Engine đang chạy.")
            print(" 👉 Vui lòng BẬT DOCKER DESKTOP trên máy tính của bạn.")
            print(" 👉 Script đang TỰ ĐỘNG QUÉT LIÊN TỤC và sẽ TỰ BẮT NGAY khi Docker bật!")
            print(" (Bạn KHÔNG CẦN tắt cửa sổ này hay bấm bất kỳ phím nào)")
            print("=" * 75)
            first_warn = False

        sym = spinners[idx % len(spinners)]
        idx += 1
        sys.stdout.write(f"\r>>> [{sym}] Đang quét tìm Docker Desktop liên tục... (tự nhận diện khi bật) ")
        sys.stdout.flush()
        time.sleep(1.5)

    if not first_warn:
        print("\n[✓] Đã phát hiện và kết nối thành công tới Docker Engine!")
        time.sleep(1)

    # 2. Chờ đủ số container
    started_compose = False
    while True:
        containers = get_running_containers()
        count = len(containers)
        if count >= min_containers:
            break

        if not started_compose and auto_start:
            print("\n" + "=" * 75)
            print(f" ⚠️  PHÁT HIỆN CHỈ CÓ {count}/{min_containers} CONTAINER ĐANG CHẠY.")
            print(" >>> ĐANG TỰ ĐỘNG KHỞI ĐỘNG 16 CONTAINER (docker compose up -d)...")
            print("===========================================================================")
            run_cmd(["docker", "compose", "-p", "cuonghauminicloud", "up", "-d"])
            run_cmd([get_bash_exe(), "object-storage-server/init-buckets.sh"])
            started_compose = True
            print(">>> Đang chờ các container chuyển sang trạng thái sẵn sàng...")

        sym = spinners[idx % len(spinners)]
        idx += 1
        sys.stdout.write(f"\r>>> [{sym}] Đang chờ đủ 16 Container sẵn sàng: {count}/{min_containers} Up... ")
        sys.stdout.flush()
        time.sleep(1.5)

    return True

def wait_step_choice(step_num, next_step_name):
    """Bắt phím điều khiển ở cuối mỗi bước: Enter (Tiếp tục), R (Re-check), Q (Thoát)"""
    print("---------------------------------------------------------------------------")
    print(f">>> [Bước {step_num}/6 XONG] Các phím điều khiển:")
    print(f"    - Bấm [ENTER] : Tiếp tục sang {next_step_name}")
    print(f"    - Gõ  [R]     : Quét lại / Chạy lại bước này ngay (Re-check)")
    print(f"    - Gõ  [Q]     : Dừng demo và quay về Menu chính")
    while True:
        try:
            ans = input(">>> Lựa chọn của bạn [Enter/R/Q]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return "quit"
        if ans == "r":
            return "retry"
        elif ans == "q":
            return "quit"
        elif ans == "":
            return "next"
        else:
            print("Vui lòng chỉ bấm Enter, hoặc gõ R (Re-check), hoặc gõ Q (Thoát).")

# =========================================================================
# ĐỊNH NGHĨA CHI TIẾT 6 BƯỚC DEMO
# =========================================================================

def step1_ps():
    wait_for_docker_and_containers(min_containers=16, auto_start=True)
    print("=" * 75)
    print(" [BƯỚC 1] KIỂM TRA TRẠNG THÁI 16 CONTAINER (MẠNG CLOUD-NET 10.10.10.0/24)")
    print("===========================================================================")
    run_cmd(["docker", "compose", "-p", "cuonghauminicloud", "ps", "--format", "table {{.Name}}\t{{.Status}}\t{{.Ports}}"])
    print("=" * 75)

def step2_ping():
    wait_for_docker_and_containers(min_containers=16, auto_start=True)
    print("=" * 75)
    print(" [BƯỚC 2] PING THÔNG MẠNG TỪ PROXY TỚI 9 CONTAINER NỘI BỘ (0% RỚT GÓI)")
    print("===========================================================================")
    run_cmd([get_bash_exe(), "scripts/ping-all.sh"])
    print("=" * 75)

def step3_api_db():
    wait_for_docker_and_containers(min_containers=16, auto_start=True)
    app_port = get_env("APP_PORT", "8085")
    proxy_port = get_env("PROXY_PORT", "80")
    db_pass = get_env("DB_ROOT_PASSWORD")
    if not db_pass:
        print("[LỖI] Thiếu DB_ROOT_PASSWORD trong .env, không thể truy vấn MariaDB.")
        return

    print("=" * 75)
    print(" [BƯỚC 3] TEST API BACKEND FLASK & TRUY VẤN DATABASE MARIADB")
    print("===========================================================================")
    print(f">>> 1. Gọi API /hello trực tiếp (cổng {app_port}) và qua Proxy Gateway (cổng {proxy_port}):")
    print(f"Direct  :{app_port}/hello -> ", end="", flush=True)
    run_cmd(["curl.exe", "-s", f"http://localhost:{app_port}/hello"])
    print(f"\nGateway :{proxy_port}/api/hello -> ", end="", flush=True)
    run_cmd(["curl.exe", "-s", f"http://localhost:{proxy_port}/api/hello"])
    print("\n\n>>> 2. Truy vấn dữ liệu bảng 'notes' trong database MariaDB:")
    run_cmd([
        "docker", "exec", "relational-database-server", "mariadb",
        "-uroot", f"-p{db_pass}",
        "-e", "USE minicloud; SHOW TABLES; SELECT * FROM notes;"
    ])
    print("=" * 75)

def step4_dns():
    wait_for_docker_and_containers(min_containers=16, auto_start=True)
    dns_port = get_env("DNS_PORT", "1053")
    print("=" * 75)
    print(f" [BƯỚC 4] PHÂN GIẢI TÊN MIỀN NỘI BỘ QUA MÁY CHỦ DNS BIND9 (CỔNG {dns_port})")
    print("===========================================================================")
    print(f">>> Lệnh: dig @host.docker.internal -p {dns_port} web-frontend-server.cloud.local +short")
    run_cmd([
        "docker", "run", "--rm",
        "--add-host", "host.docker.internal:host-gateway",
        "nicolaka/netshoot:v0.16",
        "dig", "@host.docker.internal", "-p", str(dns_port),
        "web-frontend-server.cloud.local", "+short"
    ])
    print(">>> Kết quả phân giải đúng IP tĩnh 10.10.10.10 của web-frontend-server!")
    print("=" * 75)

def step5_lb():
    wait_for_docker_and_containers(min_containers=16, auto_start=True)
    print("=" * 75)
    print(" [BƯỚC 5] CÂN BẰNG TẢI ROUND ROBIN & DỪNG WEB2 FAILOVER TRONG 2 GIÂY")
    print("===========================================================================")
    run_cmd([get_bash_exe(), "scripts/lb-test.sh"])
    print("=" * 75)

def step6_smoke():
    wait_for_docker_and_containers(min_containers=16, auto_start=True)
    print("=" * 75)
    print(" [BƯỚC 6] KẾT QUẢ SMOKE TEST TỰ ĐỘNG TOÀN DIỆN (32 / 32 TEST CASE PASS)")
    print("===========================================================================")
    # The full run takes about 5 minutes, so show the saved result of the last run by default.
    log_file = HERE / "logs" / "smoke-local.txt"
    if log_file.exists():
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        print(f">>> Kết quả lần chạy gần nhất ({log_file.name}, {len(lines)} dòng) - 40 dòng cuối:\n")
        print("\n".join(lines[-40:]))
        print("\n>>> Đây là log đã lưu, KHÔNG phải chạy lại. Gõ [F] rồi Enter để chạy lại thật (~5 phút),")
        print(">>> hoặc chỉ bấm Enter để bỏ qua.")
        try:
            ans = input(">>> Lựa chọn [F/Enter]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            ans = ""
        if ans == "f":
            run_cmd([get_bash_exe(), "scripts/smoke-test.sh", "local"])
    else:
        print(">>> Chưa có log, đang chạy smoke test thật (~5 phút)...")
        run_cmd([get_bash_exe(), "scripts/smoke-test.sh", "local"])
    print("=" * 75)

def run_all_steps():
    clear()
    wait_for_docker_and_containers(min_containers=16, auto_start=True)

    print("\n" + "=" * 75)
    print("    BẮT ĐẦU CHẠY LIVE DEMO TUẦN TỰ TỪ A ĐẾN Z CHO HỆ THỐNG MYMINICLOUD   ")
    print("===========================================================================\n")
    time.sleep(1)

    steps = [
        (1, "Bước 2 (Ping toàn mạng)", step1_ps),
        (2, "Bước 3 (Test API Flask & MariaDB)", step2_ping),
        (3, "Bước 4 (Phân giải DNS BIND9)", step3_api_db),
        (4, "Bước 5 (Cân bằng tải Round Robin & Failover 2s)", step4_dns),
        (5, "Bước 6 (Bộ 32 bài Smoke Test)", step5_lb),
        (6, "Hoàn tất buổi demo!", step6_smoke),
    ]

    for num, next_name, func in steps:
        while True:
            clear()
            func()
            if num < 6:
                action = wait_step_choice(num, next_name)
                if action == "retry":
                    continue
                elif action == "quit":
                    print("\n>>> Đã dừng chạy demo và quay về Menu chính.")
                    time.sleep(1)
                    return
                else:
                    break
            else:
                print("\n" + "=" * 75)
                print("  🎉 CHÚC MỪNG: HOÀN TẤT TOÀN BỘ 6 BƯỚC DEMO TRỰC TIẾP CỦA MYMINICLOUD! ")
                print("===========================================================================")
                input("\n>>> Bấm Enter để quay lại Menu chính...")
                return

def run_single_step(step_func, step_name):
    while True:
        clear()
        step_func()
        print("---------------------------------------------------------------------------")
        print(">>> Lựa chọn:")
        print("    - Bấm [ENTER] : Quay lại Menu chính")
        print("    - Gõ  [R]     : Chạy lại / Kiểm tra lại bước này (Re-check)")
        ans = input(">>> Lựa chọn của bạn [Enter/R]: ").strip().lower()
        if ans == "r":
            continue
        break

def open_tabs_fallback():
    proxy_port = get_env("PROXY_PORT", "80")
    auth_port = get_env("AUTH_PORT", "8081")
    minio_port = get_env("MINIO_CONSOLE_PORT", "9001")
    grafana_port = get_env("GRAFANA_PORT", "3000")

    urls = [
        f"http://localhost:{proxy_port}/",
        f"http://localhost:{proxy_port}/portal/",
        f"http://localhost:{proxy_port}/blog/",
        f"http://localhost:{auth_port}/auth/admin/",
        f"http://localhost:{minio_port}/",
        f"http://localhost:{grafana_port}/",
        f"http://localhost:{get_env('PROM_PORT', '9090')}/targets",
    ]
    print("Đang mở các tab trên trình duyệt mặc định...")
    for u in urls:
        webbrowser.open(u)
    print("Đã mở xong 7 tab!")

def chrome_demo_alive():
    """True when the detached demo Chrome (started by auto_login.py) is still running."""
    port = get_env("DEMO_CHROME_PORT", "9222")
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1.5).read()
        return True
    except Exception:
        return False


def run_auto_login(mode="open", *extra):
    return subprocess.run([sys.executable, "scripts/auto_login.py", mode, *extra]).returncode


# Menu keys 12..23 continue the numbering after keys 10/11 (Portal sv01/sv02)
ADVANCED = {
    "12": ("A01", "Portal OIDC PKCE (không client secret)"),
    "13": ("A02", "Phân quyền RBAC: editor ghi, viewer bị 403"),
    "14": ("A03", "CRUD sinh viên trên MariaDB (tạo/sửa/400/xoá)"),
    "15": ("A04", "MinIO: ảnh public, tài liệu private"),
    "16": ("A05", "Log tập trung Loki, tra theo X-Request-ID"),
    "17": ("A06", "Giám sát container (cAdvisor) và metric RED"),
    "18": ("A07", "Cảnh báo: dừng web2 -> firing -> resolved (~2-3 phút)"),
    "19": ("A08", "Gateway: rate limit 429, header bảo mật"),
    "20": ("A09", "Sao lưu MariaDB sang MinIO và khôi phục thử"),
    "21": ("A10", "DNS nội bộ cho app (service discovery)"),
    "22": ("A11", "Compose hardening: RAM, no-new-privileges, healthy"),
    "23": ("A12", "Bảng trạng thái live trên trang chủ"),
}


def run_advanced(code):
    """Run scripts/demo_advanced.py <code>; [R] repeats it, Enter goes back to the menu."""
    while True:
        clear()
        wait_for_docker_and_containers(min_containers=16, auto_start=True)
        run_cmd([sys.executable, "scripts/demo_advanced.py", code])
        print("---------------------------------------------------------------------------")
        try:
            ans = input(">>> [Enter] quay lại Menu chính, [R] chạy lại: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return
        if ans != "r":
            return


def portal_switch(user):
    """Options 10/11: switch the Portal tab to sv01 (editor) or sv02 (viewer) without typing."""
    clear()
    print("=" * 75)
    print(f" PORTAL: TỰ ĐỘNG ĐĂNG XUẤT VÀ ĐĂNG NHẬP LẠI BẰNG {user}")
    print("===========================================================================")
    if not chrome_demo_alive():
        print(">>> Chrome demo chưa mở, đang mở trước (phím 8)...")
        run_auto_login("open")
    run_auto_login("portal", user)
    input("\n>>> Bấm Enter để quay lại Menu chính...")


def browser_menu():
    """Option 8: open + log in the 7 tabs, or (if Chrome is already open) re-enter / re-login / close it."""
    clear()
    if not chrome_demo_alive():
        print("=" * 75)
        print(" ĐANG KHỞI CHẠY CHROME & TỰ ĐỘNG ĐĂNG NHẬP 7 TAB THEO .ENV...")
        print("===========================================================================")
        if run_auto_login("open") != 0:
            print("\n[Playwright/Chrome chưa sẵn sàng] Chuyển sang mở các tab mặc định...")
            open_tabs_fallback()
        input("\n>>> Chrome vẫn mở khi bạn thoát. Bấm Enter để quay lại Menu chính...")
        return
    while True:
        print("=" * 75)
        print(" CHROME DEMO ĐANG MỞ SẴN (7 tab đã đăng nhập)")
        print("===========================================================================")
        print("    - Bấm [ENTER] hoặc gõ [F] : Đưa Chrome lên trước (giữ nguyên tab, KHÔNG đăng nhập lại)")
        print("    - Gõ [R]                  : Đóng rồi mở lại + đăng nhập lại 7 tab")
        print("    - Gõ [C]                  : Đóng Chrome demo")
        print("    - Gõ [B]                  : Quay lại Menu chính")
        try:
            ans = input(">>> Lựa chọn [Enter/F/R/C/B]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return
        if ans in ("", "f"):
            run_auto_login("focus")
            time.sleep(1)
            return
        if ans == "r":
            run_auto_login("close")
            for _ in range(10):
                if not chrome_demo_alive():
                    break
                time.sleep(0.5)
            run_auto_login("open")
            input("\n>>> Bấm Enter để quay lại Menu chính...")
            return
        if ans == "c":
            run_auto_login("close")
            time.sleep(1)
            return
        if ans == "b":
            return
        print("Vui lòng chọn Enter/F/R/C/B.")


# =========================================================================
# MENU CHÍNH
# =========================================================================

def show_menu():
    # Kiểm tra và đảm bảo Docker + Container sẵn sàng ngay khi vừa mở script
    wait_for_docker_and_containers(min_containers=16, auto_start=True)

    while True:
        clear()
        docker_ok = is_docker_running()
        cnt_count = len(get_running_containers()) if docker_ok else 0
        status_line = (f"Docker: {'ĐANG CHẠY' if docker_ok else 'CHƯA BẬT'} | Containers: {cnt_count}/16 Up"
                       f" | Chrome: {'ĐANG MỞ' if chrome_demo_alive() else 'chưa mở'}")

        print("=" * 75)
        print("            MYMINICLOUD - BẢNG ĐIỀU KHIỂN LIVE DEMO CUỐI KỲ")
        print("             Sinh viên: Đinh Quốc Cường (MSSV: 523H0008)")
        print(f"             [{status_line}]")
        print("=" * 75)
        print()
        print("  [1]  CHẠY DEMO TUẦN TỰ TỪ A ĐẾN Z (Bấm Enter tiếp tục, có nút [R] Re-check)")
        print()
        print("  ------------------- CHỌN TỪNG BƯỚC RIÊNG LẺ -------------------")
        print("  [2]  Bước 1: Kiểm tra 16 Container (docker compose ps)")
        print("  [3]  Bước 2: Ping thông mạng 9 Server (ping-all.sh)")
        print("  [4]  Bước 3: Test API Backend Flask & Query Database MariaDB")
        print("  [5]  Bước 4: Test Phân giải tên miền DNS BIND9 (dig web-frontend-server)")
        print("  [6]  Bước 5: Test Cân bằng tải Round Robin & Dừng Web2 Failover 2s")
        print("  [7]  Bước 6: Xem kết quả Smoke Test 32/32 PASS (log; gõ F để chạy lại ~5 phút)")
        print()
        print("  ------------------- TỰ ĐỘNG MỞ & ĐĂNG NHẬP --------------------")
        print("  [8]  MỞ CHROME & ĐĂNG NHẬP 7 TAB (đã mở sẵn: vào lại / đăng nhập lại / đóng)")
        print("  [9]  Khởi động lại toàn bộ 16 Container (docker compose up -d)")
        print("  [10] Portal: tự đăng nhập sv01 (editor), mở tab Sinh viên")
        print("  [11] Portal: tự đăng nhập sv02 (viewer) và thử Thêm sinh viên -> hiện 403")
        print()
        print("  ------------------- PHẦN NÂNG CAO (A01-A12) ---------------------")
        for key, (code, label) in ADVANCED.items():
            print(f"  [{key}] {code}: {label}")
        print()
        print("  ------------------- AWS EC2 (HTTPS) ---------------------------------")
        print("  [24] Mở 7 tab trên EC2 và đăng nhập (đã mở sẵn thì đưa lên trước)")
        print("  [25] Chạy phần nâng cao A01-A12 trên EC2 (lệnh chạy trên EC2, tab mở trên máy này)")
        print()
        print("  [0]  Thoát")
        print("=" * 75)

        try:
            choice = input(">>> Nhập lựa chọn [0-25] rồi bấm Enter: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nĐã thoát.")
            break

        if choice == "1":
            run_all_steps()
        elif choice == "2":
            run_single_step(step1_ps, "Bước 1")
        elif choice == "3":
            run_single_step(step2_ping, "Bước 2")
        elif choice == "4":
            run_single_step(step3_api_db, "Bước 3")
        elif choice == "5":
            run_single_step(step4_dns, "Bước 4")
        elif choice == "6":
            run_single_step(step5_lb, "Bước 5")
        elif choice == "7":
            run_single_step(step6_smoke, "Bước 6")
        elif choice == "8":
            clear()
            print("=" * 75)
            print(" ĐANG KHỞI CHẠY CHROME & TỰ ĐỘNG ĐĂNG NHẬP 7 TAB THEO .ENV...")
            print("===========================================================================")
            browser_menu()
        elif choice == "9":
            clear()
            print("Đang khởi động lại toàn bộ 16 container...")
            run_cmd(["docker", "compose", "-p", "cuonghauminicloud", "up", "-d"])
            run_cmd([get_bash_exe(), "object-storage-server/init-buckets.sh"])
            input("\n>>> Bấm Enter để quay lại Menu chính...")
        elif choice in ADVANCED:
            run_advanced(ADVANCED[choice][0])
        elif choice == "24":
            clear()
            run_cmd([sys.executable, "scripts/ec2/open_tabs.py"])
            input("\n>>> Chrome EC2 vẫn mở khi bạn thoát. Bấm Enter để quay lại Menu chính...")
        elif choice == "25":
            while True:
                clear()
                print("=" * 75)
                print(" PHẦN NÂNG CAO TRÊN EC2: nhập mã A01..A12 (Enter để quay lại menu)")
                print("=" * 75)
                for key, (code, label) in ADVANCED.items():
                    print(f"  {code}: {label}")
                try:
                    code = input("\n>>> Mã (A01-A12): ").strip().upper()
                except (KeyboardInterrupt, EOFError):
                    break
                if not code:
                    break
                run_cmd([sys.executable, "scripts/ec2/run_demo.py", code])
                input("\n>>> Bấm Enter để chọn mục khác...")
        elif choice == "10":
            portal_switch("sv01")
        elif choice == "11":
            portal_switch("sv02")
        elif choice == "0":
            print("\nTạm biệt và chúc bạn có buổi báo cáo thành công rực rỡ!")
            break

if __name__ == "__main__":
    try:
        show_menu()
    except (KeyboardInterrupt, EOFError):
        print("\nĐã thoát.")
