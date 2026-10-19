import json
import os
import time

import pymysql
import requests
from flask import Flask, jsonify, render_template_string, request
from jose import jwt

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


app = Flask(__name__)
app.json.ensure_ascii = False


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
def secure():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify(error="Missing Bearer token"), 401
    token = auth.split(" ", 1)[1]
    try:
        issuer = jwt.get_unverified_claims(token).get("iss")
        if issuer not in OIDC_ISSUERS:
            return jsonify(error=f"Untrusted issuer: {issuer}"), 401
        payload = jwt.decode(
            token,
            signing_key_for(token),
            algorithms=["RS256"],
            audience=OIDC_AUDIENCE,
            issuer=issuer,
        )
    except Exception as e:
        return jsonify(error=str(e)), 401
    return jsonify(
        message="Secure resource OK",
        preferred_username=payload.get("preferred_username"),
        issuer=payload.get("iss"),
        audience=payload.get("aud"),
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8081)
