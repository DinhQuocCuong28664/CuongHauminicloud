import datetime
import functools
import hmac
import json
import logging
import os
import re
import sys
import time
import uuid

import boto3
import pymysql
import requests
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from flask import Flask, Response, g, jsonify, render_template_string, request
from jose import jwt
from prometheus_client import (CONTENT_TYPE_LATEST, REGISTRY, CollectorRegistry, Counter, Histogram,
                               generate_latest, multiprocess)

STUDENTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "students.json")

# Bảng HTML khi mở API bằng trình duyệt; curl và client khác vẫn nhận JSON
TABLE_PAGE = """<!DOCTYPE html>
<html lang="vi"><head><meta charset="utf-8"><title>{{ title }}</title>
<style>
  body { font-family: "Segoe UI", Arial, sans-serif; background: #f5f7fb; margin: 40px; color: #1c2333; }
  h2 { color: {{ color }}; }
  table { border-collapse: collapse; min-width: 640px; background: #fff; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
  th { background: {{ color }}; color: #fff; text-align: left; padding: 10px 14px; }
  td { padding: 9px 14px; border-bottom: 1px solid #e3e8f0; }
  p { color: #5b6475; font-size: 14px; }
</style></head><body>
<h2>{{ title }}</h2>
<table>
  <tr>{% for c in columns %}<th>{{ c }}</th>{% endfor %}</tr>
  {% for row in rows %}<tr>{% for c in columns %}<td>{{ row[c] }}</td>{% endfor %}</tr>{% endfor %}
</table>
<p>Nguồn: {{ data_source }} · application-backend-server</p>
</body></html>"""


def wants_html():
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "text/html" and request.accept_mimetypes[best] > request.accept_mimetypes["application/json"]


def table_or_json(title, color, source, columns, rows):
    if wants_html():
        return render_template_string(
            TABLE_PAGE, title=title, color=color, data_source=source, columns=columns, rows=rows
        )
    return jsonify(rows)

# ---------- Cấu hình OIDC (Keycloak) ----------
KC_INTERNAL_URL = os.getenv("KC_INTERNAL_URL", "http://authentication-identity-server:8080/auth")
KC_REALM = os.getenv("KC_REALM", "realm_523H0008_523H0025")
OIDC_AUDIENCE = os.getenv("OIDC_AUDIENCE", "flask-app")
# JWKS lấy qua mạng nội bộ cloud-net
OIDC_JWKS_URL = os.getenv(
    "OIDC_JWKS_URL", f"{KC_INTERNAL_URL}/realms/{KC_REALM}/protocol/openid-connect/certs"
)
# Issuer (claim "iss") là URL mà client đã dùng để xin token, tức URL công khai
# (qua proxy hoặc qua cổng 8081), nên khác URL nội bộ ở trên. Liệt kê các issuer hợp lệ, cách nhau dấu phẩy.
OIDC_ISSUERS = [s.strip() for s in os.getenv("OIDC_ISSUERS", "").split(",") if s.strip()]

# ---------- Cấu hình database ----------
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "relational-database-server"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "minicloud_app"),
    "password": os.getenv("DB_PASSWORD", ""),
    "connect_timeout": 5,
    "cursorclass": pymysql.cursors.DictCursor,
}

# ---------- Nâng cao: object storage (MinIO, API S3) ----------
# App dùng user MinIO riêng chỉ có quyền trên profile-pics và documents (giống IAM role tối thiểu)
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://object-storage-server:9000")
AVATAR_BUCKET = os.getenv("AVATAR_BUCKET", "profile-pics")
DOCUMENT_BUCKET = os.getenv("DOCUMENT_BUCKET", "documents")
AVATAR_MAX_BYTES = 2 * 1024 * 1024
# Nhận dạng ảnh theo vài byte đầu file, không tin phần mở rộng hay Content-Type do trình duyệt gửi
IMAGE_SIGNATURES = {b"\xff\xd8\xff": ("jpg", "image/jpeg"), b"\x89PNG\r\n\x1a\n": ("png", "image/png")}

# ---------- Nâng cao: cảnh báo từ Alertmanager ----------
ALERT_WEBHOOK_TOKEN = os.getenv("ALERT_WEBHOOK_TOKEN", "")

# ---------- Nâng cao: metric Prometheus (RED: Rate, Errors, Duration) ----------
# gunicorn chạy nhiều worker: mỗi worker ghi metric ra PROMETHEUS_MULTIPROC_DIR, /metrics gộp lại
REQUESTS = Counter("minicloud_http_requests_total", "Số request HTTP tới API", ["method", "endpoint", "status"])
LATENCY = Histogram(
    "minicloud_http_request_duration_seconds", "Thời gian xử lý request", ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
NOT_MEASURED = {"/metrics", "/health"}

# ---------- Nâng cao: log JSON một dòng, có request_id để Loki truy vết qua proxy và app ----------
log = logging.getLogger("minicloud")
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter("%(message)s"))
log.addHandler(_handler)
log.setLevel(logging.INFO)
log.propagate = False


def log_json(level, msg, **fields):
    record = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds"),
              "level": level, "service": "application-backend-server", "msg": msg}
    record.update({k: v for k, v in fields.items() if v is not None})
    log.log(logging.ERROR if level == "error" else logging.INFO, json.dumps(record, ensure_ascii=False))


_jwks = None
_jwks_fetched_at = 0


def get_jwks():
    """Tải JWKS của realm, cache 10 phút."""
    global _jwks, _jwks_fetched_at
    now = time.time()
    if not _jwks or now - _jwks_fetched_at > 600:
        _jwks = requests.get(OIDC_JWKS_URL, timeout=5).json()
        _jwks_fetched_at = now
    return _jwks


def signing_key_for(token):
    """Chọn khoá công khai theo kid trong header của token."""
    kid = jwt.get_unverified_header(token).get("kid")
    for key in get_jwks().get("keys", []):
        if key.get("kid") == kid:
            return key
    raise ValueError(f"No signing key found for kid={kid}")


def db_query(sql, database, args=None):
    conn = pymysql.connect(database=database, **DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall()
    finally:
        conn.close()


def db_exec(sql, database, args=None):
    """Câu lệnh ghi (INSERT/UPDATE/DELETE): commit và trả (lastrowid, rowcount)."""
    conn = pymysql.connect(database=database, **DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args)
        conn.commit()
        return cur.lastrowid, cur.rowcount
    finally:
        conn.close()


_s3 = None


def s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client(
            "s3", endpoint_url=S3_ENDPOINT, region_name="us-east-1",
            aws_access_key_id=os.getenv("S3_ACCESS_KEY"), aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
            config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"},
                              connect_timeout=3, read_timeout=10, retries={"max_attempts": 2}),
        )
    return _s3


app = Flask(__name__)
app.json.ensure_ascii = False
app.config["MAX_CONTENT_LENGTH"] = AVATAR_MAX_BYTES + 64 * 1024


@app.before_request
def _start_request():
    g.t0 = time.perf_counter()
    # Proxy gắn X-Request-ID cho mỗi request; gọi thẳng cổng 8085 thì app tự sinh
    g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    g.user = None


@app.after_request
def _finish_request(resp):
    endpoint = request.url_rule.rule if request.url_rule else "unmatched"
    duration = time.perf_counter() - g.t0
    if endpoint not in NOT_MEASURED:
        REQUESTS.labels(request.method, endpoint, str(resp.status_code)).inc()
        LATENCY.labels(request.method, endpoint).observe(duration)
        log_json("error" if resp.status_code >= 500 else "warn" if resp.status_code >= 400 else "info",
                 "request", request_id=g.request_id, method=request.method, path=request.path,
                 endpoint=endpoint, status=resp.status_code, duration_ms=round(duration * 1000, 1), user=g.user)
    resp.headers["X-Request-ID"] = g.request_id
    return resp


# ---------- Xác thực và phân quyền (RBAC) bằng access token của Keycloak ----------
class AuthError(Exception):
    def __init__(self, message, status=401):
        super().__init__(message)
        self.status = status


def verify_token():
    """Kiểm tra issuer tin cậy, chữ ký RS256 theo kid, audience; trả về claims."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise AuthError("Missing Bearer token")
    token = auth.split(" ", 1)[1]
    try:
        issuer = jwt.get_unverified_claims(token).get("iss")
        if issuer not in OIDC_ISSUERS:
            raise AuthError(f"Untrusted issuer: {issuer}")
        return jwt.decode(token, signing_key_for(token), algorithms=["RS256"],
                          audience=OIDC_AUDIENCE, issuer=issuer)
    except AuthError:
        raise
    except Exception as e:
        raise AuthError(str(e)) from e


def require_auth(role=None):
    """Decorator: bắt buộc token hợp lệ; nếu có role thì token phải chứa realm role đó (không có -> 403)."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                claims = verify_token()
            except AuthError as e:
                return jsonify(error=str(e)), e.status
            g.claims = claims
            g.user = claims.get("preferred_username")
            g.roles = claims.get("realm_access", {}).get("roles", [])
            if role and role not in g.roles:
                return jsonify(error=f"Forbidden: cần realm role '{role}'", roles=g.roles), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ================================================================ Endpoint của đề bài
@app.get("/hello")
def hello():
    return jsonify(message="Hello from App Server!")


@app.get("/health")
def health():
    return jsonify(status="ok", service="application-backend-server")


@app.get("/notes")
def notes():
    """Đọc bảng minicloud.notes để kiểm tra kết nối App -> DB."""
    try:
        rows = db_query("SELECT id, title, created_at FROM notes ORDER BY id", "minicloud")
    except pymysql.MySQLError as e:
        return jsonify(error=f"Database error: {e}"), 503
    for row in rows:
        row["created_at"] = row["created_at"].isoformat(sep=" ")
    return jsonify(source="MariaDB minicloud.notes", count=len(rows), notes=rows)


@app.get("/student")
def student():
    """Mở rộng 2: danh sách sinh viên đọc từ file JSON."""
    with open(STUDENTS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return table_or_json(
        "Danh sách sinh viên (JSON)", "#5b3cc4", "students.json",
        ["id", "name", "major", "gpa"], data,
    )


@app.get("/students-db")
def students_db():
    """Mở rộng 3: danh sách sinh viên đọc từ MariaDB studentdb.students."""
    try:
        rows = db_query(
            "SELECT id, student_id, fullname, dob, major FROM students ORDER BY id", "studentdb"
        )
    except pymysql.MySQLError as e:
        return jsonify(error=f"Database error: {e}"), 503
    for row in rows:
        row["dob"] = row["dob"].isoformat() if row["dob"] else None
    return table_or_json(
        "Danh sách sinh viên (MariaDB)", "#1a8f3c", "MariaDB studentdb.students",
        ["id", "student_id", "fullname", "dob", "major"], rows,
    )


@app.get("/secure")
@require_auth()
def secure():
    return jsonify(
        message="Secure resource OK",
        preferred_username=g.claims.get("preferred_username"),
        issuer=g.claims.get("iss"),
        audience=g.claims.get("aud"),
    )


# ================================================================ Nâng cao
@app.get("/metrics")
def metrics():
    """Metric cho Prometheus (job app). Gateway chặn đường này từ bên ngoài."""
    if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    else:
        registry = REGISTRY
    return Response(generate_latest(registry), mimetype=CONTENT_TYPE_LATEST)


def avatar_key(username):
    """Ảnh đại diện hiện có của user (jpg hoặc png) trong bucket public, hoặc None."""
    for ext in ("jpg", "png"):
        key = f"{username}.{ext}"
        try:
            head = s3().head_object(Bucket=AVATAR_BUCKET, Key=key)
            return key, head["ETag"].strip('"')[:12]
        except (ClientError, BotoCoreError):
            continue
    return None, None


@app.get("/me")
@require_auth()
def me():
    c = g.claims
    key, version = avatar_key(g.user)
    return jsonify(
        username=g.user, name=c.get("name"), family_name=c.get("family_name"), given_name=c.get("given_name"),
        email=c.get("email"), roles=g.roles,
        issuer=c.get("iss"), audience=c.get("aud"), client=c.get("azp"),
        issued_at=c.get("iat"), expires_at=c.get("exp"),
        avatar_url=f"/media/{key}?v={version}" if key else None,
    )


# ---------- CRUD sinh viên (A03): đọc cần đăng nhập, ghi cần role editor ----------
STUDENT_ID_RE = re.compile(r"^[A-Za-z0-9]{3,10}$")
STUDENT_COLS = "id, student_id, fullname, dob, major"


def student_row(row):
    row["dob"] = row["dob"].isoformat() if row["dob"] else None
    return row


def validate_student(data):
    """Trả về (giá trị đã chuẩn hoá, None) hoặc (None, thông báo lỗi)."""
    if not isinstance(data, dict):
        return None, "Body phải là JSON object"
    sid = str(data.get("student_id", "")).strip()
    name = str(data.get("fullname", "")).strip()
    major = str(data.get("major", "") or "").strip()
    dob = data.get("dob") or None
    if not STUDENT_ID_RE.match(sid):
        return None, "student_id gồm 3–10 chữ hoặc số"
    if not 1 <= len(name) <= 100:
        return None, "fullname dài 1–100 ký tự"
    if len(major) > 50:
        return None, "major tối đa 50 ký tự"
    if dob is not None:
        try:
            dob = datetime.date.fromisoformat(str(dob)).isoformat()
        except ValueError:
            return None, "dob phải có dạng YYYY-MM-DD"
    return (sid, name, dob, major or None), None


def student_id_taken(sid, exclude_id=None):
    rows = db_query("SELECT id FROM students WHERE student_id = %s", "studentdb", (sid,))
    return any(r["id"] != exclude_id for r in rows)


@app.get("/students")
@require_auth()
def students_list():
    rows = db_query(f"SELECT {STUDENT_COLS} FROM students ORDER BY id", "studentdb")
    return jsonify(source="MariaDB studentdb.students", count=len(rows), students=[student_row(r) for r in rows])


@app.post("/students")
@require_auth("editor")
def students_create():
    values, err = validate_student(request.get_json(silent=True))
    if err:
        return jsonify(error=err), 400
    if student_id_taken(values[0]):
        return jsonify(error=f"student_id {values[0]} đã tồn tại"), 409
    new_id, _ = db_exec("INSERT INTO students (student_id, fullname, dob, major) VALUES (%s, %s, %s, %s)",
                        "studentdb", values)
    row = db_query(f"SELECT {STUDENT_COLS} FROM students WHERE id = %s", "studentdb", (new_id,))[0]
    log_json("info", "student created", request_id=g.request_id, user=g.user, student_id=values[0])
    return jsonify(student_row(row)), 201, {"Location": f"/api/students/{new_id}"}


@app.put("/students/<int:sid>")
@require_auth("editor")
def students_update(sid):
    if not db_query("SELECT id FROM students WHERE id = %s", "studentdb", (sid,)):
        return jsonify(error=f"Không có sinh viên id={sid}"), 404
    values, err = validate_student(request.get_json(silent=True))
    if err:
        return jsonify(error=err), 400
    if student_id_taken(values[0], exclude_id=sid):
        return jsonify(error=f"student_id {values[0]} đã tồn tại"), 409
    db_exec("UPDATE students SET student_id = %s, fullname = %s, dob = %s, major = %s WHERE id = %s",
            "studentdb", (*values, sid))
    row = db_query(f"SELECT {STUDENT_COLS} FROM students WHERE id = %s", "studentdb", (sid,))[0]
    log_json("info", "student updated", request_id=g.request_id, user=g.user, id=sid)
    return jsonify(student_row(row))


@app.delete("/students/<int:sid>")
@require_auth("editor")
def students_delete(sid):
    _, count = db_exec("DELETE FROM students WHERE id = %s", "studentdb", (sid,))
    if not count:
        return jsonify(error=f"Không có sinh viên id={sid}"), 404
    log_json("info", "student deleted", request_id=g.request_id, user=g.user, id=sid)
    return "", 204


# ---------- Ảnh đại diện (A04): upload qua app vào bucket public, đọc qua gateway /media/ ----------
@app.post("/avatar")
@require_auth()
def avatar_upload():
    f = request.files.get("file")
    if f is None:
        return jsonify(error="Thiếu file (multipart field 'file')"), 400
    data = f.read(AVATAR_MAX_BYTES + 1)
    if len(data) > AVATAR_MAX_BYTES:
        return jsonify(error="Ảnh tối đa 2 MB"), 413
    kind = next((v for sig, v in IMAGE_SIGNATURES.items() if data.startswith(sig)), None)
    if kind is None:
        return jsonify(error="Chỉ nhận ảnh JPEG hoặc PNG"), 415
    ext, content_type = kind
    key = f"{g.user}.{ext}"
    s3().put_object(Bucket=AVATAR_BUCKET, Key=key, Body=data, ContentType=content_type,
                    CacheControl="public, max-age=60")
    # Xoá bản định dạng còn lại để mỗi user chỉ có một ảnh
    other = f"{g.user}.{'png' if ext == 'jpg' else 'jpg'}"
    s3().delete_object(Bucket=AVATAR_BUCKET, Key=other)
    _, version = avatar_key(g.user)
    log_json("info", "avatar uploaded", request_id=g.request_id, user=g.user, key=key, bytes=len(data))
    return jsonify(bucket=AVATAR_BUCKET, key=key, bytes=len(data), url=f"/media/{key}?v={version}"), 201


# ---------- Tài liệu private (A04): chỉ editor tải được, app đọc thay người dùng ----------
@app.get("/documents")
@require_auth("editor")
def documents_list():
    resp = s3().list_objects_v2(Bucket=DOCUMENT_BUCKET)
    items = [{"name": o["Key"], "bytes": o["Size"], "modified": o["LastModified"].isoformat()}
             for o in resp.get("Contents", [])]
    return jsonify(bucket=DOCUMENT_BUCKET, count=len(items), documents=items)


@app.get("/documents/<path:name>")
@require_auth("editor")
def documents_get(name):
    try:
        obj = s3().get_object(Bucket=DOCUMENT_BUCKET, Key=name)
    except ClientError:
        return jsonify(error=f"Không có tài liệu {name}"), 404
    log_json("info", "document downloaded", request_id=g.request_id, user=g.user, key=name)
    return Response(obj["Body"].iter_chunks(64 * 1024), mimetype=obj.get("ContentType", "application/octet-stream"),
                    headers={"Content-Disposition": f'attachment; filename="{os.path.basename(name)}"',
                             "Content-Length": str(obj["ContentLength"])})


# ---------- Cảnh báo (A07): Alertmanager gọi webhook, Portal đọc lại ----------
@app.post("/alerts")
def alerts_webhook():
    sent = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not ALERT_WEBHOOK_TOKEN or not hmac.compare_digest(sent, ALERT_WEBHOOK_TOKEN):
        return jsonify(error="Invalid webhook token"), 401
    payload = request.get_json(silent=True) or {}
    for a in payload.get("alerts", []):
        labels, ann = a.get("labels", {}), a.get("annotations", {})
        starts = a.get("startsAt", "")[:19].replace("T", " ") or None
        ends = a.get("endsAt", "")[:19].replace("T", " ")
        ends = None if not ends or ends.startswith("0001") else ends
        db_exec(
            "INSERT INTO alerts (fingerprint, alertname, severity, target, status, summary, starts_at, ends_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            " ON DUPLICATE KEY UPDATE status = VALUES(status), summary = VALUES(summary),"
            " ends_at = VALUES(ends_at), received_at = CURRENT_TIMESTAMP",
            "ops",
            (a.get("fingerprint"), labels.get("alertname"), labels.get("severity"),
             labels.get("name") or labels.get("instance") or labels.get("job"),
             a.get("status"), ann.get("summary"), starts, ends),
        )
        log_json("warn" if a.get("status") == "firing" else "info", "alert received",
                 request_id=g.request_id, alertname=labels.get("alertname"), alert_status=a.get("status"))
    return jsonify(received=len(payload.get("alerts", [])))


@app.get("/alerts")
@require_auth("editor")
def alerts_list():
    rows = db_query(
        "SELECT alertname, severity, target, status, summary, starts_at, ends_at, received_at"
        " FROM alerts ORDER BY received_at DESC LIMIT 30", "ops")
    # Mọi mốc thời gian lưu theo UTC (Alertmanager gửi UTC, MariaDB chạy múi giờ UTC)
    for r in rows:
        for k in ("starts_at", "ends_at", "received_at"):
            r[k] = r[k].isoformat() + "Z" if r[k] else None
    firing = sum(1 for r in rows if r["status"] == "firing")
    return jsonify(firing=firing, alerts=rows)


@app.errorhandler(413)
def too_large(_e):
    return jsonify(error="Request quá lớn (tối đa 2 MB)"), 413


@app.errorhandler(pymysql.MySQLError)
def db_error(e):
    log_json("error", "database error", request_id=g.get("request_id"), error=str(e))
    return jsonify(error=f"Database error: {e}"), 503


@app.errorhandler(ClientError)
def s3_error(e):
    log_json("error", "object storage error", request_id=g.get("request_id"), error=str(e))
    return jsonify(error=f"Object storage error: {e.response.get('Error', {}).get('Code')}"), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8081)
