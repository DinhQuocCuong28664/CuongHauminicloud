#!/usr/bin/env bash
# remote-check.sh — kiểm thử MyMiniCloud trên EC2 từ máy cá nhân, qua Internet (đúng như người dùng bên ngoài).
#   bash scripts/ec2/remote-check.sh        Kết quả ghi vào evidence/ec2-remote-check.txt
set -u
export MSYS_NO_PATHCONV=1
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
. scripts/ec2/instance.env
set -a; . ./.env; set +a
if python3 -c 'pass' >/dev/null 2>&1; then PY=python3; else PY=python; fi
export PYTHONUTF8=1
# curl của Git Bash là bản Windows: không ghi được vào /dev/null, nên bỏ nội dung vào file tạm trong dự án
NUL=logs/.remote-check.tmp
IP=$PUBLIC_IP
DOMAIN="$(printf '%s' "$IP" | tr . -).sslip.io"
D="https://$DOMAIN"

line() { printf '%-50s -> %s\n' "$1" "$2"; }
code() { curl -s -o "$NUL" -m 8 -w '%{http_code}' "$@"; }

{
echo "Kiểm thử từ máy cá nhân ($(curl -s https://checkip.amazonaws.com | tr -d '\r\n')) tới EC2 $IP ($DOMAIN) — $(date '+%Y-%m-%d %H:%M:%S %z')"
echo
echo "### HTTPS (cổng 443 mở cho Internet; cổng 80 chỉ chuyển hướng)"
line "GET http://$IP/" "$(curl -s -o "$NUL" -m 8 -w '%{http_code} %{redirect_url}' "http://$IP/")"
line "GET http://$DOMAIN/portal/" "$(curl -s -o "$NUL" -m 8 -w '%{http_code} %{redirect_url}' "http://$DOMAIN/portal/")"
# curl bản Windows dùng Schannel, không in thông tin chứng chỉ: đọc bằng openssl
cert=$(echo | openssl s_client -connect "$DOMAIN:443" -servername "$DOMAIN" 2>/dev/null \
       | openssl x509 -noout -subject -issuer -enddate 2>/dev/null | tr -d '\r' | tr '\n' ';')
line "Chứng chỉ của $DOMAIN" "$cert"
line "Header HSTS" "$(curl -s -D - -o "$NUL" "$D/" | tr -d '\r' | awk -F': ' 'tolower($1)=="strict-transport-security"{print $2}')"
echo
echo "### Qua reverse proxy bằng HTTPS"
line "GET $D/" "$(code "$D/") $(curl -s "$D/" | grep -o '<title>[^<]*</title>')"
line "GET $D/blog/blog1.html" "$(code "$D/blog/blog1.html")"
line "GET $D/portal/" "$(code "$D/portal/") $(curl -s "$D/portal/" | grep -o '<title>[^<]*</title>')"
line "GET $D/api/hello" "$(curl -s "$D/api/hello")"
line "GET $D/student/" "$(curl -s "$D/student/" | $PY -c 'import sys,json; print(len(json.load(sys.stdin)), "sinh viên")')"
line "GET $D/api/students-db" "$(curl -s "$D/api/students-db" | $PY -c 'import sys,json; print(len(json.load(sys.stdin)), "bản ghi từ MariaDB")')"
line "GET $D/auth/" "$(curl -s -o "$NUL" -w '%{http_code} %{redirect_url}' "$D/auth/")"
lb=$(for i in 1 2 3 4; do curl -s -D - -o "$NUL" "$D/" | tr -d '\r' | awk 'tolower($1)=="x-served-by:"{print $2}'; done | tr '\n' ' ')
line "4 request liên tiếp, header X-Served-By" "$lb"
TOKEN=$(curl -s -X POST "$D/auth/realms/$KC_REALM/protocol/openid-connect/token" \
          -d grant_type=password -d "client_id=$OIDC_CLIENT_ID" -d username=sv01 --data-urlencode "password=$SV_PASSWORD" \
        | $PY -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
ISS=$(printf '%s' "$TOKEN" | $PY -c "
import sys, json, base64
p = sys.stdin.read().split('.')[1]; p += '=' * (-len(p) % 4); print(json.loads(base64.urlsafe_b64decode(p))['iss'])")
line "issuer của token sv01" "$ISS"
line "GET /api/secure (token sv01)" "$(curl -s -w ' [%{http_code}]' "$D/api/secure" -H "Authorization: Bearer $TOKEN" | tr -d '\n')"
line "GET /api/me (token sv01)" "$(curl -s "$D/api/me" -H "Authorization: Bearer $TOKEN" | $PY -c "import sys,json; d=json.load(sys.stdin); print(d['username'], d['roles'], d.get('avatar_url'))")"
line "GET /api/secure (không token)" "$(curl -s -w ' [%{http_code}]' "$D/api/secure" | tr -d '\n')"
echo
echo "### Cổng trực tiếp (Security Group chỉ mở cho My IP)"
line "Web1  http://$IP:8080/" "$(code "http://$IP:8080/")"
line "Web2  http://$IP:8088/" "$(code "http://$IP:8088/")"
line "App   http://$IP:8085/hello" "$(curl -s -m 8 "http://$IP:8085/hello")"
line "Keycloak http://$IP:8081/auth/" "$(code "http://$IP:8081/auth/")"
line "MinIO public http://$IP:9000/profile-pics/avatar.jpg" "$(code "http://$IP:9000/profile-pics/avatar.jpg")"
line "MinIO private http://$IP:9000/documents/report.pdf" "$(code "http://$IP:9000/documents/report.pdf")"
line "MinIO Console http://$IP:9001/" "$(code "http://$IP:9001/")"
line "Prometheus http://$IP:9090/-/ready" "$(code "http://$IP:9090/-/ready")"
line "Alertmanager http://$IP:9093/-/ready" "$(code "http://$IP:9093/-/ready")"
line "Grafana http://$IP:3000/api/health" "$(code "http://$IP:3000/api/health")"
echo
echo "### Cổng KHÔNG mở trong Security Group (phải bị chặn)"
for p in 3306 9100; do
  r=$(curl -s -o "$NUL" -m 5 -w '%{http_code}' "http://$IP:$p/" 2>&1); rc=$?
  line "TCP $IP:$p" "$([ "$rc" -eq 28 ] && echo 'timeout (bị Security Group chặn)' || echo "rc=$rc http=$r")"
done
} 2>&1 | tr -d '\r' | tee evidence/ec2-remote-check.txt
rm -f "$NUL"
