#!/usr/bin/env bash
# remote-check.sh — kiểm thử MyMiniCloud trên EC2 từ máy cá nhân, qua public IP (đúng như người dùng ngoài Internet).
#   bash scripts/ec2/remote-check.sh        Kết quả ghi vào evidence/ec2-remote-check.txt
set -u
export MSYS_NO_PATHCONV=1
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
. scripts/ec2/instance.env
set -a; . ./.env; set +a
if python3 -c 'pass' >/dev/null 2>&1; then PY=python3; else PY=python; fi
IP=$PUBLIC_IP

line() { printf '%-46s -> %s\n' "$1" "$2"; }
code() { curl -s -o /dev/null -m 8 -w '%{http_code}' "$@"; }

{
echo "Kiểm thử từ máy cá nhân ($(curl -s https://checkip.amazonaws.com | tr -d '\r\n')) tới EC2 $IP — $(date '+%Y-%m-%d %H:%M:%S %z')"
echo
echo "### Qua reverse proxy (cổng 80, mở cho Internet)"
line "GET http://$IP/" "$(code "http://$IP/") $(curl -s "http://$IP/" | grep -o '<title>[^<]*</title>')"
line "GET http://$IP/blog/" "$(code "http://$IP/blog/")"
line "GET http://$IP/blog/blog1.html" "$(code "http://$IP/blog/blog1.html")"
line "GET http://$IP/api/hello" "$(curl -s "http://$IP/api/hello")"
line "GET http://$IP/student/" "$(curl -s "http://$IP/student/" | $PY -c 'import sys,json; print(len(json.load(sys.stdin)), "sinh viên")')"
line "GET http://$IP/api/students-db" "$(curl -s "http://$IP/api/students-db" | $PY -c 'import sys,json; print(len(json.load(sys.stdin)), "bản ghi từ MariaDB")')"
line "GET http://$IP/auth/" "$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' "http://$IP/auth/")"
lb=$(for i in 1 2 3 4; do curl -s -D - -o /dev/null "http://$IP/" | tr -d '\r' | awk 'tolower($1)=="x-served-by:"{print $2}'; done | tr '\n' ' ')
line "4 request liên tiếp, header X-Served-By" "$lb"
TOKEN=$(curl -s -X POST "http://$IP/auth/realms/$KC_REALM/protocol/openid-connect/token" \
          -d grant_type=password -d "client_id=$OIDC_CLIENT_ID" -d username=sv01 --data-urlencode "password=$SV_PASSWORD" \
        | $PY -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
line "GET /api/secure (token sv01 xin qua $IP)" "$(curl -s -w ' [%{http_code}]' "http://$IP/api/secure" -H "Authorization: Bearer $TOKEN" | tr -d '\n')"
line "GET /api/secure (không token)" "$(curl -s -w ' [%{http_code}]' "http://$IP/api/secure" | tr -d '\n')"
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
line "Grafana http://$IP:3000/api/health" "$(code "http://$IP:3000/api/health")"
echo
echo "### Cổng KHÔNG mở trong Security Group (phải bị chặn)"
for p in 3306 9100; do
  r=$(curl -s -o /dev/null -m 5 -w '%{http_code}' "http://$IP:$p/" 2>&1); rc=$?
  line "TCP $IP:$p" "$([ "$rc" -eq 28 ] && echo 'timeout (bị Security Group chặn)' || echo "rc=$rc http=$r")"
done
} 2>&1 | tr -d '\r' | tee evidence/ec2-remote-check.txt
