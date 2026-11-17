#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""demo_advanced.py - live demo of one advanced feature (A01..A12) against the local stack.

Usage: python scripts/demo_advanced.py A01   (A01..A12)
Each demo mirrors the matching T-A test in smoke-advanced.sh and prints the evidence step by step.
Data written by a demo is removed again (A03 deletes the student it creates).
"""
import concurrent.futures
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent.parent
os.chdir(HERE)
os.environ["MSYS_NO_PATHCONV"] = "1"
os.environ["COMPOSE_PROJECT_NAME"] = "cuonghauminicloud"

ENV = {}
for line in (HERE / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        ENV[k.strip()] = v.strip().strip('"').strip("'")

# DEMO_BASE overrides the gateway address, e.g. on EC2: DEMO_BASE=https://<dashed-ip>.sslip.io (plain HTTP there
# only redirects to HTTPS)
# DEMO_TARGET=ec2 (set by scripts/ec2/run_demo.py): HTTP checks go to the EC2 instance over HTTPS, docker commands
# run on the instance through SSH, and the browser steps still open on THIS Windows machine (EC2 Chrome, port 9223).
TARGET = os.environ.get("DEMO_TARGET", "local")
SSH_PREFIX = []
if TARGET == "ec2":
    _inst = dict(l.split("=", 1) for l in (HERE / "scripts" / "ec2" / "instance.env").read_text(encoding="utf-8").splitlines() if "=" in l)
    EC2_IP = _inst["PUBLIC_IP"].strip()
    P = f"https://{EC2_IP.replace('.', '-')}.sslip.io"
    PROM = f"http://{EC2_IP}:{ENV.get('PROM_PORT', '9090')}"
    GRAFANA = f"http://{EC2_IP}:{ENV.get('GRAFANA_PORT', '3000')}"
    MINIO_API = f"http://{EC2_IP}:{ENV.get('MINIO_API_PORT', '9000')}"
    MINIO_CONSOLE = f"http://{EC2_IP}:{ENV.get('MINIO_CONSOLE_PORT', '9001')}"
    SSH_PREFIX = ["ssh", "-n", "-i", str(HERE / "scripts" / "ec2" / _inst["KEY_FILE"].strip()),
                  "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={HERE / 'scripts' / 'ec2' / 'known_hosts'}",
                  "-o", "ConnectTimeout=10", "-o", "LogLevel=ERROR", f"ubuntu@{EC2_IP}"]
else:
    P = os.environ.get("DEMO_BASE") or f"http://localhost:{ENV.get('PROXY_PORT', '80')}"
    PROM = f"http://localhost:{ENV.get('PROM_PORT', '9090')}"
    GRAFANA = f"http://localhost:{ENV.get('GRAFANA_PORT', '3000')}"
    MINIO_API = f"http://localhost:{ENV.get('MINIO_API_PORT', '9000')}"
    MINIO_CONSOLE = f"http://localhost:{ENV.get('MINIO_CONSOLE_PORT', '9001')}"
REALM = ENV["KC_REALM"]
CLIENT = ENV["OIDC_CLIENT_ID"]
NETSHOOT = "nicolaka/netshoot:v0.16"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def http(method, url, headers=None, body=None, follow=True, timeout=15):
    """Return (status, body bytes, headers dict). HTTP errors are returned, not raised."""
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)
    except Exception as e:  # connection problems
        return 0, str(e).encode(), {}


def jbody(raw):
    try:
        return json.loads(raw)
    except Exception:
        return {}


def token(user):
    data = urllib.parse.urlencode({"grant_type": "password", "client_id": CLIENT, "username": user,
                                   "password": ENV["SV_PASSWORD"]}).encode()
    st, raw, _ = http("POST", f"{P}/auth/realms/{REALM}/protocol/openid-connect/token", body=data)
    return jbody(raw).get("access_token", "")


def bearer(tok):
    return {"Authorization": f"Bearer {tok}"}


def jreq(method, path, tok, payload=None):
    time.sleep(0.2)   # stay under the gateway rate limit (10 req/s per IP) that A08 demonstrates
    h = dict(bearer(tok)) if tok else {}
    data = None
    if payload is not None:
        h["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
    return http(method, f"{P}{path}", headers=h, body=data)


def title(code, text):
    print("=" * 75)
    print(f" [{code}] {text}")
    print("=" * 75)


# Same DEMO_PACE as demo_browser.py: a short pause after every result line so the audience can read it
PACE = float(os.environ.get("DEMO_PACE") or ENV.get("DEMO_PACE") or "2")


def line(ok, text):
    print(f"  [{'PASS' if ok else 'FAIL'}] {text}", flush=True)
    time.sleep(0.4 * PACE)


def remote(cmd):
    """On EC2 mode a docker command runs on the instance (ssh, project directory); locally it is unchanged."""
    if TARGET == "ec2" and cmd and cmd[0] == "docker":
        import shlex
        return SSH_PREFIX + ["cd ~/CuongHauminicloud && " + shlex.join(cmd)]
    return cmd


def sh(cmd, capture=True):
    cmd = remote(cmd)
    r = subprocess.run(cmd, capture_output=capture, text=True, encoding="utf-8", errors="replace")
    return (r.stdout or "").strip()


def chrome_goto(url):
    """Show a page in the demo Chrome (started by DEMO.bat key 8); silently skipped when it is not open."""
    url = url.replace("localhost:80/", "localhost/")   # same tab as the one DEMO.bat opened
    r = subprocess.run([sys.executable, "scripts/auto_login.py", "goto", url], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode == 0:
        print(f"  >>> Đã mở trong Chrome demo: {url}")
    else:
        print(f"  >>> Chrome demo chưa mở (phím 8). Mở tay: {url}")


def browser(action):
    """Let the demo Chrome show the same thing (see demo_browser.py); skipped when Chrome is not open."""
    print("  --- Trình duyệt ---")
    subprocess.run([sys.executable, "scripts/demo_browser.py", action])


def prom_value(query):
    st, raw, _ = http("GET", f"{PROM}/api/v1/query?" + urllib.parse.urlencode({"query": query}))
    res = jbody(raw).get("data", {}).get("result", [])
    return res[0]["value"][1] if res else "none"


# ------------------------------------------------------------------------------------------------ demos
def a01():
    title("A01", "OIDC Authorization Code + PKCE cho Portal (không dùng client secret)")
    auth = (f"{P}/auth/realms/{REALM}/protocol/openid-connect/auth?client_id=portal&response_type=code&scope=openid"
            f"&redirect_uri={urllib.parse.quote(P + '/portal/', safe='')}")
    st1, _, _ = http("GET", auth + "&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&code_challenge_method=S256")
    line(st1 == 200, f"Yêu cầu đăng nhập CÓ code_challenge S256 -> HTTP {st1} (hiện trang đăng nhập)")
    st2, _, hd = http("GET", auth, follow=False)
    loc = hd.get("Location", "")
    line(st2 in (302, 400), f"Yêu cầu THIẾU code_challenge -> bị từ chối ({st2} {loc.split('?')[0] or ''}"
         + (" error=" + loc.split("error=")[1].split("&")[0] if "error=" in loc else "") + ")")
    data = urllib.parse.urlencode({"grant_type": "password", "client_id": "portal", "username": "sv01",
                                   "password": ENV["SV_PASSWORD"]}).encode()
    st3, raw, _ = http("POST", f"{P}/auth/realms/{REALM}/protocol/openid-connect/token", body=data)
    err = jbody(raw).get("error")
    line(err == "unauthorized_client", f"Đăng nhập bằng mật khẩu trực tiếp với client portal -> {err}")
    st4, _, hd4 = http("GET", f"{P}/portal/")
    csp = hd4.get("Content-Security-Policy", "")
    line("default-src 'self'" in csp, "Trang /portal/ có Content-Security-Policy: default-src 'self'")
    browser("a01")


def a02():
    title("A02", "RBAC: sv01 (editor) được ghi, sv02 (viewer) chỉ đọc")
    t1, t2 = token("sv01"), token("sv02")
    claims = lambda t: jbody(__import__("base64").urlsafe_b64decode(t.split(".")[1] + "=" * (-len(t.split(".")[1]) % 4)))
    roles = lambda t: [r for r in claims(t).get("realm_access", {}).get("roles", []) if r in ("editor", "viewer")]
    print(f"  Role trong token: sv01={roles(t1)}  sv02={roles(t2)}")
    line(jreq("GET", "/api/students", "")[0] == 401, "GET /api/students không token -> 401")
    line(jreq("GET", "/api/students", t2)[0] == 200, "GET /api/students sv02 -> 200 (viewer được đọc)")
    st, raw, _ = jreq("POST", "/api/students", t2, {"student_id": "SV990", "fullname": "Viewer"})
    line(st == 403, f"POST /api/students sv02 -> {st}: {jbody(raw).get('error', '')}")
    line(jreq("GET", "/api/documents", t2)[0] == 403, "GET /api/documents sv02 -> 403 (chỉ editor tải tài liệu)")
    line(jreq("GET", "/api/documents", t1)[0] == 200, "GET /api/documents sv01 -> 200")
    print("  --- Trình duyệt ---")
    subprocess.run([sys.executable, "scripts/auto_login.py", "portal", "sv02"])


def a03():
    title("A03", "CRUD sinh viên trên MariaDB (tạo, sửa, dữ liệu sai, xoá)")
    t1 = token("sv01")
    st, raw, _ = jreq("POST", "/api/students", t1,
                      {"student_id": "SV990", "fullname": "Demo CRUD", "dob": "2005-05-05", "major": "Cloud"})
    sid = jbody(raw).get("id")
    line(st == 201, f"POST /api/students -> {st} (id {sid})")
    st, _, _ = jreq("PUT", f"/api/students/{sid}", t1,
                    {"student_id": "SV990", "fullname": "Demo CRUD", "dob": "2005-05-05", "major": "DevOps"})
    line(st == 200, f"PUT  /api/students/{sid} đổi ngành sang DevOps -> {st}")
    st, _, _ = jreq("POST", "/api/students", t1, {"student_id": "!", "fullname": ""})
    line(st == 400, f"POST dữ liệu sai (mã '!', tên rỗng) -> {st} (kiểm tra dữ liệu)")
    st, _, _ = jreq("DELETE", f"/api/students/{sid}", t1)
    line(st == 204, f"DELETE /api/students/{sid} -> {st}")
    st, _, _ = jreq("DELETE", f"/api/students/{sid}", t1)
    line(st == 404, f"DELETE lần hai -> {st}")
    print("  (Sinh viên SV990 đã được xoá, dữ liệu trở lại như cũ.)")
    browser("a03")


def a04():
    title("A04", "MinIO qua app: ảnh đại diện public, tài liệu private, presigned/tải có quyền")
    t1, t2 = token("sv01"), token("sv02")
    sample = HERE / "object-storage-server" / "samples" / "avatar.jpg"
    if sample.exists():
        boundary = "----demoboundary7MA4YWxk"
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"avatar.jpg\"\r\n"
                f"Content-Type: image/jpeg\r\n\r\n").encode() + sample.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        h = dict(bearer(t2))
        h["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        st, raw, _ = http("POST", f"{P}/api/avatar", headers=h, body=body)
        url = jbody(raw).get("url", "")
        line(st in (200, 201) and url, f"POST /api/avatar (sv02, ảnh JPEG mẫu; không đụng ảnh của sv01) -> {st} {url}")
        if url:
            st, _, hd = http("GET", f"{P}{url}")
            line(st == 200, f"GET {url} -> {st} {hd.get('Content-Type', '')} (đọc qua /media/)")
    st, raw, _ = http("GET", f"{P}/api/documents", headers=bearer(t1))
    line(st == 200, f"GET /api/documents (sv01) -> {st}")
    st, raw, _ = http("GET", f"{P}/api/documents/report.pdf", headers=bearer(t1))
    line(st == 200 and len(raw) > 100000, f"Tải report.pdf bằng sv01 -> {st}, {len(raw)} byte")
    line(http("GET", f"{P}/api/documents/report.pdf")[0] == 401, "Tải report.pdf không token -> 401")
    line(http("GET", f"{P}/api/documents/report.pdf", headers=bearer(t2))[0] == 403, "Tải report.pdf bằng sv02 (viewer) -> 403")
    st, _, _ = http("GET", f"{MINIO_API}/documents/report.pdf")
    line(st == 403, f"Truy cập thẳng MinIO documents/report.pdf ẩn danh -> {st} (bucket private)")
    st, _, _ = http("GET", f"{MINIO_API}/profile-pics/avatar.jpg")
    line(st == 200, f"Truy cập thẳng profile-pics/avatar.jpg ẩn danh -> {st} (bucket public)")
    browser("a04")


def a05():
    title("A05", "Log tập trung (Alloy + Loki): tra một request theo X-Request-ID")
    st, _, hd = http("GET", f"{P}/api/students-db")
    rid = next((v for k, v in hd.items() if k.lower() == "x-request-id"), "")
    print(f"  GET /api/students-db -> {st}, X-Request-ID = {rid}")
    print("  Đang hỏi Loki (log về sau vài giây, tối đa 60 giây)...")
    n_proxy = n_app = 0
    for i in range(12):
        time.sleep(5)
        counts = []
        for svc in ("api-gateway-proxy-server", "application-backend-server"):
            out = sh(["docker", "run", "--rm", "--network", "cloud-net", NETSHOOT, "curl", "-s", "-G",
                      "http://logging-loki-server:3100/loki/api/v1/query_range",
                      "--data-urlencode", f'query={{service="{svc}"}} |= "{rid}"',
                      "--data-urlencode", "since=10m", "--data-urlencode", "limit=100"])
            try:
                counts.append(sum(len(s["values"]) for s in json.loads(out)["data"]["result"]))
            except Exception:
                counts.append(0)
        n_proxy, n_app = counts
        print(f"    sau {(i + 1) * 5}s: proxy={n_proxy} dòng, app={n_app} dòng")
        if n_proxy and n_app:
            break
    line(n_proxy >= 1 and n_app >= 1, f"Cùng request_id tìm thấy ở proxy ({n_proxy}) và app ({n_app})")
    # Open the trace panel with request_id already filled in (no copy and paste, no scrolling)
    panel = ""
    try:
        import base64
        cred = base64.b64encode(f"{ENV['GF_ADMIN_USER']}:{ENV['GF_ADMIN_PASSWORD']}".encode()).decode()
        st_g, raw_g, _ = http("GET", f"{GRAFANA}/api/dashboards/uid/logs-523h0008-523h0025",
                              headers={"Authorization": f"Basic {cred}"})
        pid = next(p["id"] for p in jbody(raw_g)["dashboard"]["panels"] if "request_id" in p.get("title", ""))
        panel = f"&viewPanel=panel-{pid}"
    except Exception:
        pass   # fall back to the whole dashboard; the request_id is still pre-filled
    chrome_goto(f"{GRAFANA}/d/logs-523h0008-523h0025/logs-e28093-myminicloud-loki?orgId=1&from=now-15m&to=now"
                f"&var-request_id={rid}{panel}")
    print(f"  request_id đã được điền sẵn trên dashboard: {rid}")


def a06():
    title("A06", "Giám sát từng container (cAdvisor) và metric RED của API")
    st, raw, _ = http("GET", f"{PROM}/api/v1/targets")
    jobs = {t["labels"]["job"]: t["health"] for t in jbody(raw).get("data", {}).get("activeTargets", [])}
    for j in ("cadvisor", "app", "alertmanager", "loki"):
        line(jobs.get(j) == "up", f"Target {j}: {jobs.get(j, 'không có')}")
    n = prom_value('count(time() - container_last_seen{container_label_com_docker_compose_project="cuonghauminicloud"} < 60)')
    line(n != "none" and int(float(n)) >= 16, f"cAdvisor đang theo dõi {n} container")
    total = prom_value("sum(minicloud_http_requests_total)")
    errors = prom_value('sum(minicloud_http_requests_total{status=~"5.."})')
    p95 = prom_value("histogram_quantile(0.95, sum by (le) (rate(minicloud_http_request_duration_seconds_bucket[5m])))")
    print(f"  Tổng request API đã đếm (Rate): {total}")
    print(f"  Lỗi 5xx (Errors): {errors}")
    print(f"  p95 thời gian xử lý 5 phút (Duration): {p95} s")
    chrome_goto(f"{GRAFANA}/d/api-red-523h0008-523h0025/api-e28093-red-metrics-application-backend-server")


def a07():
    title("A07", "Cảnh báo tự động: dừng web2 -> WebServerDown firing -> bật lại -> resolved (~2-3 phút)")
    t1 = token("sv01")
    since = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())

    def state():
        st, raw, _ = http("GET", f"{P}/api/alerts", headers=bearer(t1))
        for a in jbody(raw).get("alerts", []):
            if a["alertname"] == "WebServerDown" and a["target"] == "web-frontend-server2" and (a["starts_at"] or "") >= since:
                return a["status"]
        return "none"

    browser("ops")
    try:
        print("  >>> docker stop web-frontend-server2")
        sh(["docker", "stop", "web-frontend-server2"])
        t0 = time.time()
        while time.time() - t0 < 150:
            if state() == "firing":
                break
            print(f"    đang chờ Alertmanager gửi firing... {int(time.time() - t0)}s")
            time.sleep(10)
        fired = state() == "firing"
        browser("ops")
        line(fired, f"App nhận cảnh báo WebServerDown FIRING sau {int(time.time() - t0)}s")
        st, _, _ = http("GET", f"{P}/")
        line(st == 200, f"Trong lúc web2 dừng, GET / qua proxy vẫn -> {st} (web1 phục vụ)")
        print("  (Xem thêm: Portal > tab Vận hành, hoặc Prometheus > Alerts)")
    finally:
        print("  >>> docker start web-frontend-server2")
        sh(["docker", "start", "web-frontend-server2"])
    t1_ = time.time()
    while time.time() - t1_ < 150:
        if state() == "resolved":
            break
        print(f"    đang chờ trạng thái resolved... {int(time.time() - t1_)}s")
        time.sleep(10)
    line(state() == "resolved", f"App nhận cảnh báo RESOLVED sau {int(time.time() - t1_)}s")
    browser("ops")


def a08():
    title("A08", "Gateway: rate limit 10 req/s mỗi IP (429), header bảo mật, chặn đường dẫn nội bộ")

    def hit(_):
        return http("GET", f"{P}/api/hello", timeout=10)[0]

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        codes = list(ex.map(hit, range(40)))
    summary = {c: codes.count(c) for c in sorted(set(codes))}
    line(429 in summary and 200 in summary, f"40 request /api/hello song song (20 luồng) -> {summary} (429 = bị giới hạn tốc độ)")
    time.sleep(3)
    _, _, hd = http("GET", f"{P}/api/hello")
    names = {k.lower() for k in hd}
    for h in ("x-request-id", "x-content-type-options", "x-frame-options", "referrer-policy"):
        line(h in names, f"Header {h}")
    line(http("GET", f"{P}/api/metrics")[0] == 404, "GET /api/metrics -> 404 (metric nội bộ không lộ ra ngoài)")
    line(http("POST", f"{P}/api/alerts")[0] == 403, "POST /api/alerts không token -> 403")
    print("  (HTTPS Let's Encrypt chỉ có trên EC2: https://<ip>.sslip.io)")
    browser("a08")
    time.sleep(4)   # let the rate-limit window clear so the next demo key is not answered with 429


def a09():
    title("A09", "Sao lưu MariaDB sang MinIO (gzip + SHA-256, xoá sau 7 ngày) và khôi phục thử")
    print("  >>> Sao lưu:")
    subprocess.run(remote(["docker", "compose", "--profile", "ops", "run", "--rm", "db-backup"]))
    print("\n  >>> Khôi phục thử và so sánh checksum:")
    subprocess.run(remote(["docker", "compose", "--profile", "ops", "run", "--rm", "--entrypoint", "python", "db-backup",
                           "/app/restore.py"]))
    browser("minio")
    print(f"  (Mở tay: {MINIO_CONSOLE}/login, đăng nhập rồi vào bucket db-backups.)")


def a10():
    title("A10", "Service discovery: app gọi DB và MinIO bằng tên cloud.local do BIND9 phân giải")
    print("  Biến môi trường của app:", sh(["docker", "exec", "application-backend-server", "printenv", "DB_HOST", "S3_ENDPOINT"]).replace("\n", "  "))
    d1 = sh(["docker", "exec", "application-backend-server", "getent", "hosts", "db.cloud.local"])
    d2 = sh(["docker", "exec", "application-backend-server", "getent", "hosts", "s3.cloud.local"])
    line(d1.startswith("10.10.10.30"), f"getent hosts db.cloud.local -> {d1}")
    line(d2.startswith("10.10.10.50"), f"getent hosts s3.cloud.local -> {d2}")
    st, _, _ = http("GET", f"{P}/api/notes")
    line(st == 200, f"GET /api/notes (app đọc DB qua db.cloud.local) -> {st}")
    chrome_goto(f"{P}/api/notes")


def a11():
    title("A11", "Compose hardening: giới hạn RAM, no-new-privileges, healthcheck")
    ids = sh(["docker", "compose", "ps", "-q"]).split()
    fmt = "{{.Name}}|{{.HostConfig.Memory}}|{{.HostConfig.SecurityOpt}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}}"
    rows = [sh(["docker", "inspect", "--format", fmt, i]).lstrip("/").split("|") for i in ids]
    print(f"  {'CONTAINER':<40}{'RAM (MB)':>9}  {'no-new-priv':<12}health")
    ok_mem = ok_sec = healthy = 0
    for name, mem, sec, health in sorted(rows):
        mb = int(mem) // (1024 * 1024) if mem.isdigit() else 0
        nnp = "no-new-privileges" in sec
        ok_mem += mb > 0
        ok_sec += nnp
        healthy += health == "healthy"
        print(f"  {name:<40}{mb:>9}  {'có' if nnp else 'KHÔNG':<12}{health}")
    n = len(rows)
    line(ok_mem == n, f"Giới hạn RAM: {ok_mem}/{n} container")
    line(ok_sec == n, f"no-new-privileges: {ok_sec}/{n} container")
    line(healthy >= 14, f"Healthcheck healthy: {healthy} container (Loki và nginx-exporter không có healthcheck)")
    chrome_goto(f"{GRAFANA}/d/containers-523h0008-523h0025/containers-e28093-myminicloud-cadvisor")


def a12():
    title("A12", "Bảng trạng thái dịch vụ live trên trang chủ (tự làm mới 5 giây)")

    def web2():
        st, raw, _ = http("GET", f"{P}/api/status")
        for s in jbody(raw).get("services", []):
            if s["id"] == "web2":
                return s["status"]
        return "?"

    st, raw, _ = http("GET", f"{P}/api/status")
    summ = jbody(raw).get("summary", {})
    print(f"  GET /api/status -> {st}: {summ.get('up')}/{summ.get('total')} dịch vụ UP")
    chrome_goto(f"{P}/")
    time.sleep(2)
    try:
        print("  >>> docker stop web-frontend-server2  (nhìn thẻ web2 trên Tab 1 đổi sang đỏ)")
        sh(["docker", "stop", "web-frontend-server2"])
        t0 = time.time()
        while time.time() - t0 < 15 and web2() != "down":
            time.sleep(1)
        line(web2() == "down", f"web2 thành 'down' sau {int(time.time() - t0)}s")
        input("  Bấm Enter khi đã chỉ xong cho thầy để bật lại web2... ")
    finally:
        print("  >>> docker start web-frontend-server2")
        sh(["docker", "start", "web-frontend-server2"])
    t0 = time.time()
    while time.time() - t0 < 40 and web2() != "up":
        time.sleep(1)
    line(web2() == "up", f"web2 thành 'up' lại sau {int(time.time() - t0)}s")


DEMOS = {f"A{i:02d}": fn for i, fn in enumerate(
    (a01, a02, a03, a04, a05, a06, a07, a08, a09, a10, a11, a12), start=1)}

if __name__ == "__main__":
    key = (sys.argv[1] if len(sys.argv) > 1 else "").upper()
    if key not in DEMOS:
        print("Usage: python scripts/demo_advanced.py A01..A12")
        sys.exit(2)
    try:
        DEMOS[key]()
    except KeyboardInterrupt:
        print("\nĐã dừng.")
