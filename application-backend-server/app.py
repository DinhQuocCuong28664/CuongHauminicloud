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

# HTML table when the API is opened in a browser; curl and other clients still get JSON
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

# ---------- OIDC configuration (Keycloak) ----------
KC_INTERNAL_URL = os.getenv("KC_INTERNAL_URL", "http://authentication-identity-server:8080/auth")
KC_REALM = os.getenv("KC_REALM", "realm_523H0008_523H0025")
OIDC_AUDIENCE = os.getenv("OIDC_AUDIENCE", "flask-app")
# JWKS is fetched over the internal cloud-net network
OIDC_JWKS_URL = os.getenv(
    "OIDC_JWKS_URL", f"{KC_INTERNAL_URL}/realms/{KC_REALM}/protocol/openid-connect/certs"
)
# The issuer ("iss" claim) is the URL the client used to request the token, i.e. the public URL
# (through the proxy or port 8081), so it differs from the internal URL above. Comma-separated valid issuers.
OIDC_ISSUERS = [s.strip() for s in os.getenv("OIDC_ISSUERS", "").split(",") if s.strip()]

# ---------- Database configuration ----------
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "relational-database-server"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "minicloud_app"),
    "password": os.getenv("DB_PASSWORD", ""),
    "connect_timeout": 5,
    "cursorclass": pymysql.cursors.DictCursor,
}

# ---------- Advanced: object storage (MinIO, S3 API) ----------
# The app uses its own MinIO user with rights on profile-pics and documents only (like a least-privilege IAM role)
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://object-storage-server:9000")
AVATAR_BUCKET = os.getenv("AVATAR_BUCKET", "profile-pics")
DOCUMENT_BUCKET = os.getenv("DOCUMENT_BUCKET", "documents")
AVATAR_MAX_BYTES = 2 * 1024 * 1024
# Detect images by their first bytes; do not trust the extension or the Content-Type sent by the browser
IMAGE_SIGNATURES = {b"\xff\xd8\xff": ("jpg", "image/jpeg"), b"\x89PNG\r\n\x1a\n": ("png", "image/png")}

# ---------- Advanced: alerts from Alertmanager ----------
ALERT_WEBHOOK_TOKEN = os.getenv("ALERT_WEBHOOK_TOKEN", "")

# ---------- Advanced: Prometheus metrics (RED: Rate, Errors, Duration) ----------
# gunicorn runs several workers: each writes metrics to PROMETHEUS_MULTIPROC_DIR, /metrics merges them
REQUESTS = Counter("minicloud_http_requests_total", "HTTP requests to the API", ["method", "endpoint", "status"])
LATENCY = Histogram(
    "minicloud_http_request_duration_seconds", "Request processing time", ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
NOT_MEASURED = {"/metrics", "/health"}

# ---------- Advanced: single-line JSON log with request_id so Loki can trace across proxy and app ----------
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
    """Fetch the realm JWKS, cached for 10 minutes."""
    global _jwks, _jwks_fetched_at
    now = time.time()
    if not _jwks or now - _jwks_fetched_at > 600:
        _jwks = requests.get(OIDC_JWKS_URL, timeout=5).json()
        _jwks_fetched_at = now
    return _jwks


def signing_key_for(token):
    """Pick the public key matching the kid in the token header."""
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
    """Write statement (INSERT/UPDATE/DELETE): commit and return (lastrowid, rowcount)."""
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
    # The proxy sets X-Request-ID on every request; on direct calls to port 8085 the app generates one
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


# ---------- Authentication and authorization (RBAC) with Keycloak access tokens ----------
class AuthError(Exception):
    def __init__(self, message, status=401):
        super().__init__(message)
        self.status = status


def verify_token():
    """Check for a trusted issuer, the RS256 signature by kid and the audience; return the claims."""
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
    """Decorator: require a valid token; with a role, the token must carry that realm role (otherwise 403)."""
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
                return jsonify(error=f"Forbidden: requires realm role '{role}'", roles=g.roles), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ================================================================ Assignment endpoints
@app.get("/hello")
def hello():
    return jsonify(message="Hello from App Server!")


@app.get("/health")
def health():
    return jsonify(status="ok", service="application-backend-server")


@app.get("/notes")
def notes():
    """Read minicloud.notes to check the App -> DB connection."""
    try:
        rows = db_query("SELECT id, title, created_at FROM notes ORDER BY id", "minicloud")
    except pymysql.MySQLError as e:
        return jsonify(error=f"Database error: {e}"), 503
    for row in rows:
        row["created_at"] = row["created_at"].isoformat(sep=" ")
    return jsonify(source="MariaDB minicloud.notes", count=len(rows), notes=rows)


@app.get("/student")
def student():
    """Extension 2: student list read from a JSON file."""
    with open(STUDENTS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return table_or_json(
        "Danh sách sinh viên (JSON)", "#5b3cc4", "students.json",
        ["id", "name", "major", "gpa"], data,
    )


@app.get("/students-db")
def students_db():
    """Extension 3: student list read from MariaDB studentdb.students."""
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


# ================================================================ Advanced
@app.get("/metrics")
def metrics():
    """Metrics for Prometheus (app job). The gateway blocks this path from outside."""
    if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    else:
        registry = REGISTRY
    return Response(generate_latest(registry), mimetype=CONTENT_TYPE_LATEST)


def avatar_key(username):
    """Current avatar of the user (jpg or png) in the public bucket, or None."""
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


# ---------- Student CRUD (A03): reads need a login, writes need the editor role ----------
STUDENT_ID_RE = re.compile(r"^[A-Za-z0-9]{3,10}$")
STUDENT_COLS = "id, student_id, fullname, dob, major"


def student_row(row):
    row["dob"] = row["dob"].isoformat() if row["dob"] else None
    return row


def validate_student(data):
    """Return (normalized values, None) or (None, error message)."""
    if not isinstance(data, dict):
        return None, "Body must be a JSON object"
    sid = str(data.get("student_id", "")).strip()
    name = str(data.get("fullname", "")).strip()
    major = str(data.get("major", "") or "").strip()
    dob = data.get("dob") or None
    if not STUDENT_ID_RE.match(sid):
        return None, "student_id must be 3-10 letters or digits"
    if not 1 <= len(name) <= 100:
        return None, "fullname must be 1-100 characters"
    if len(major) > 50:
        return None, "major must be at most 50 characters"
    if dob is not None:
        try:
            dob = datetime.date.fromisoformat(str(dob)).isoformat()
        except ValueError:
            return None, "dob must use the YYYY-MM-DD format"
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
        return jsonify(error=f"student_id {values[0]} already exists"), 409
    new_id, _ = db_exec("INSERT INTO students (student_id, fullname, dob, major) VALUES (%s, %s, %s, %s)",
                        "studentdb", values)
    row = db_query(f"SELECT {STUDENT_COLS} FROM students WHERE id = %s", "studentdb", (new_id,))[0]
    log_json("info", "student created", request_id=g.request_id, user=g.user, student_id=values[0])
    return jsonify(student_row(row)), 201, {"Location": f"/api/students/{new_id}"}


@app.put("/students/<int:sid>")
@require_auth("editor")
def students_update(sid):
    if not db_query("SELECT id FROM students WHERE id = %s", "studentdb", (sid,)):
        return jsonify(error=f"No student with id={sid}"), 404
    values, err = validate_student(request.get_json(silent=True))
    if err:
        return jsonify(error=err), 400
    if student_id_taken(values[0], exclude_id=sid):
        return jsonify(error=f"student_id {values[0]} already exists"), 409
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
        return jsonify(error=f"No student with id={sid}"), 404
    log_json("info", "student deleted", request_id=g.request_id, user=g.user, id=sid)
    return "", 204


# ---------- Avatars (A04): uploaded through the app to the public bucket, read through gateway /media/ ----------
@app.post("/avatar")
@require_auth()
def avatar_upload():
    f = request.files.get("file")
    if f is None:
        return jsonify(error="Missing file (multipart field 'file')"), 400
    data = f.read(AVATAR_MAX_BYTES + 1)
    if len(data) > AVATAR_MAX_BYTES:
        return jsonify(error="Image must be at most 2 MB"), 413
    kind = next((v for sig, v in IMAGE_SIGNATURES.items() if data.startswith(sig)), None)
    if kind is None:
        return jsonify(error="Only JPEG or PNG images are accepted"), 415
    ext, content_type = kind
    key = f"{g.user}.{ext}"
    s3().put_object(Bucket=AVATAR_BUCKET, Key=key, Body=data, ContentType=content_type,
                    CacheControl="public, max-age=60")
    # Delete the other format so each user keeps a single avatar
    other = f"{g.user}.{'png' if ext == 'jpg' else 'jpg'}"
    s3().delete_object(Bucket=AVATAR_BUCKET, Key=other)
    _, version = avatar_key(g.user)
    log_json("info", "avatar uploaded", request_id=g.request_id, user=g.user, key=key, bytes=len(data))
    return jsonify(bucket=AVATAR_BUCKET, key=key, bytes=len(data), url=f"/media/{key}?v={version}"), 201


# ---------- Private documents (A04): editors only, the app reads them on behalf of the user ----------
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
        return jsonify(error=f"No document named {name}"), 404
    log_json("info", "document downloaded", request_id=g.request_id, user=g.user, key=name)
    return Response(obj["Body"].iter_chunks(64 * 1024), mimetype=obj.get("ContentType", "application/octet-stream"),
                    headers={"Content-Disposition": f'attachment; filename="{os.path.basename(name)}"',
                             "Content-Length": str(obj["ContentLength"])})


# ---------- Alerts (A07): Alertmanager calls the webhook, the Portal reads them back ----------
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
    # All timestamps are stored in UTC (Alertmanager sends UTC, MariaDB runs in UTC)
    for r in rows:
        for k in ("starts_at", "ends_at", "received_at"):
            r[k] = r[k].isoformat() + "Z" if r[k] else None
    firing = sum(1 for r in rows if r["status"] == "firing")
    return jsonify(firing=firing, alerts=rows)


@app.errorhandler(413)
def too_large(_e):
    return jsonify(error="Request too large (max 2 MB)"), 413


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
