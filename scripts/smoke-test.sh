#!/usr/bin/env bash
# smoke-test.sh — chạy các test case phần cơ bản (T-B01…T-B10), mở rộng (T-E01…T-E10)
# và nâng cao (T-A01…T-A11, trong scripts/smoke-advanced.sh), in PASS/FAIL.
# Chạy trên máy đang chạy cụm (máy local hoặc trong EC2), từ thư mục gốc dự án:
#   bash scripts/smoke-test.sh [nhãn]        ví dụ: bash scripts/smoke-test.sh local
# Kết quả ghi vào logs/smoke-<nhãn>.txt
set -u
export MSYS_NO_PATHCONV=1   # Git Bash: không đổi các tham số dạng /path

cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

LABEL=${1:-local}
H=${SMOKE_HOST:-localhost}
# URL của gateway: mặc định http://<host>:<cổng proxy>; trên EC2 có HTTPS đặt SMOKE_BASE=https://<tên miền>
P=${SMOKE_BASE:-http://$H:$PROXY_PORT}
LOG="logs/smoke-${LABEL}.txt"
NETSHOOT=nicolaka/netshoot:v0.16
DBCLIENT=mariadb:11.4.13
mkdir -p logs
exec > >(tee "$LOG") 2>&1

# Kéo trước các image công cụ (dig, mariadb client, mc) để log kéo image không lẫn vào kết quả kiểm thử
for img in "$NETSHOOT" "$DBCLIENT" pgsty/mc:RELEASE.2026-10-18T00-00-00Z; do
  docker image inspect "$img" >/dev/null 2>&1 || docker pull -q "$img" >/dev/null
done

# Trên Windows "python3" có thể là lối tắt Microsoft Store không chạy được
if python3 -c 'pass' >/dev/null 2>&1; then PY=python3; else PY=python; fi

# dig tới cổng DNS đã publish trên máy host. Docker Desktop: đi qua host.docker.internal.
# Linux (EC2): dùng mạng host, gọi 127.0.0.1 (docker-proxy chuyển vào cloud-net với nguồn là gateway
# 10.10.10.1, nằm trong ACL của bind9; còn đi từ bridge mặc định 172.17.0.0/16 sẽ bị REFUSED).
if docker info --format '{{.OperatingSystem}}' 2>/dev/null | grep -q 'Docker Desktop'; then
  dig_host() { docker run --rm --add-host host.docker.internal:host-gateway "$NETSHOOT" dig @host.docker.internal -p "$DNS_PORT" "$@"; }
else
  dig_host() { docker run --rm --network host "$NETSHOOT" dig @127.0.0.1 -p "$DNS_PORT" "$@"; }
fi

pass=0
fail=0
result() {   # result <id> <mô tả> <mã thoát 0=đạt> [chi tiết]
  if [ "$3" -eq 0 ]; then echo "[PASS] $1  $2"; pass=$((pass + 1))
  else echo "[FAIL] $1  $2"; fail=$((fail + 1)); fi
  if [ -n "${4:-}" ]; then printf '%s\n' "$4" | sed 's/^/         /'; fi
}
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
json() { $PY -c "import sys,json; d=json.load(sys.stdin); print($1)"; }

echo "MyMiniCloud smoke test — nhãn: $LABEL — host: $H — $(date '+%Y-%m-%d %H:%M:%S %z')"
echo
docker compose ps --format 'table {{.Name}}\t{{.Status}}'
echo

# ---------------------------------------------------------------- T-B01 Web
c1=$(code "http://$H:$WEB1_PORT/")
c2=$(code "http://$H:$WEB1_PORT/blog/")
t1=$(curl -s "http://$H:$WEB1_PORT/" | grep -o '<title>[^<]*</title>')
t2=$(curl -s "http://$H:$WEB1_PORT/blog/" | grep -o '<title>[^<]*</title>')
[ "$c1" = 200 ] && [ "$c2" = 200 ] && [[ "$t1" == *"MyMiniCloud – Home"* ]] && [[ "$t2" == *"MyMiniCloud – Blog"* ]]
result T-B01 "Web server: / và /blog/ trả 200" $? "GET :$WEB1_PORT/ -> $c1 $t1
GET :$WEB1_PORT/blog/ -> $c2 $t2"

# ---------------------------------------------------------------- T-B02 App
a=$(curl -s "http://$H:$APP_PORT/hello")
b=$(curl -s "$P/api/hello")
[ "$a" = "$b" ] && [[ "$a" == *"Hello from App Server!"* ]]
result T-B02 "App server: /hello trực tiếp và qua proxy giống nhau" $? "GET :$APP_PORT/hello      -> $a
GET :$PROXY_PORT/api/hello -> $b"

# ---------------------------------------------------------------- T-B03 Database
d1=$(docker exec relational-database-server mariadb -uroot -p"$DB_ROOT_PASSWORD" -e "SHOW DATABASES;" 2>&1)
d2=$(docker run --rm --network cloud-net "$DBCLIENT" mariadb -h db -uroot -p"$DB_ROOT_PASSWORD" \
       -e "USE minicloud; SHOW TABLES; SELECT * FROM notes;" 2>&1)
d3=$(curl -s "http://$H:$APP_PORT/notes")
[[ "$d1" == *minicloud* ]] && [[ "$d2" == *notes* ]] && [[ "$d2" == *"Hello from MariaDB!"* ]] && [[ "$d3" == *"Hello from MariaDB!"* ]]
result T-B03 "Database: có database minicloud, bảng notes, app đọc được" $? "$d1
$d2
GET :$APP_PORT/notes -> $d3"

# ---------------------------------------------------------------- T-B04 Authentication
k1=$(code "http://$H:$AUTH_PORT/auth/")
iss=$(curl -s "http://$H:$AUTH_PORT/auth/realms/$KC_REALM/.well-known/openid-configuration" | json "d['issuer']")
adm=$(curl -s -X POST "http://$H:$AUTH_PORT/auth/realms/master/protocol/openid-connect/token" \
        -d grant_type=password -d client_id=admin-cli -d "username=$KC_ADMIN" --data-urlencode "password=$KC_ADMIN_PASSWORD" \
      | json "d.get('access_token','')")
k2=$(code -X POST "http://$H:$AUTH_PORT/auth/admin/realms/master/users" -H "Authorization: Bearer $adm" \
        -H 'Content-Type: application/json' \
        -d '{"username":"sv-test","enabled":true,"firstName":"Smoke","lastName":"Test","email":"sv-test@cloud.local","emailVerified":true}')
k3=$(curl -s "http://$H:$AUTH_PORT/auth/admin/realms/master/users?username=sv-test&exact=true" -H "Authorization: Bearer $adm" \
      | json "len(d)")
[ "$k1" = 302 ] && [ -n "$adm" ] && { [ "$k2" = 201 ] || [ "$k2" = 409 ]; } && [ "$k3" = 1 ]
result T-B04 "Auth server: Keycloak chạy, admin đăng nhập, tạo được user" $? "GET :$AUTH_PORT/auth/ -> $k1 (chuyển tới trang đăng nhập)
issuer realm $KC_REALM: $iss
đăng nhập admin (realm master): $([ -n "$adm" ] && echo 'lấy được access token' || echo 'THẤT BẠI')
tạo user sv-test -> HTTP $k2 (201 = mới tạo, 409 = đã có); tìm lại được $k3 user"

# ---------------------------------------------------------------- T-B05 Object storage
m1=$(bash object-storage-server/init-buckets.sh 2>&1)
m2=$(code "http://$H:$MINIO_CONSOLE_PORT/")
[[ "$m1" == *index.html* ]] && [ "$m2" = 200 ]
result T-B05 "Storage: tạo bucket demo, upload index.html, console mở được" $? "$m1
GET :$MINIO_CONSOLE_PORT/ (console) -> $m2"

# ---------------------------------------------------------------- T-B06 DNS
n1=$(dig_host web-frontend-server.cloud.local +short +time=3 +tries=2 2>&1)
[ "$n1" = "10.10.10.10" ]
result T-B06 "DNS: web-frontend-server.cloud.local -> 10.10.10.10" $? "dig @<host> -p $DNS_PORT web-frontend-server.cloud.local +short -> $n1"

# ---------------------------------------------------------------- T-B07 Monitoring
p1=$(curl -s "http://$H:$PROM_PORT/api/v1/targets" \
      | json "'\n'.join(t['labels']['job']+' '+t['scrapeUrl']+' '+t['health'] for t in d['data']['activeTargets'])")
p2=$(curl -s "http://$H:$PROM_PORT/api/v1/query?query=node_cpu_seconds_total" | json "len(d['data']['result'])")
[[ "$p1" == *"node "*" up"* ]] && [ "${p2:-0}" -gt 0 ]
result T-B07 "Monitoring: target node-exporter UP, có metric node_cpu_seconds_total" $? "$p1
node_cpu_seconds_total: $p2 chuỗi thời gian"

# ---------------------------------------------------------------- T-B08 Grafana
g1=$(code "http://$H:$GRAFANA_PORT/api/health")
g2=$(curl -s -u "$GF_ADMIN_USER:$GF_ADMIN_PASSWORD" "http://$H:$GRAFANA_PORT/api/datasources/uid/prometheus/health" | json "d['status']")
g3=$(curl -s -u "$GF_ADMIN_USER:$GF_ADMIN_PASSWORD" "http://$H:$GRAFANA_PORT/api/search?type=dash-db" | json "', '.join(x['title'] for x in d)")
[ "$g1" = 200 ] && [ "$g2" = OK ] && [[ "$g3" == *"Node Exporter Full"* ]]
result T-B08 "Grafana: datasource Prometheus OK, có dashboard Node Exporter Full" $? "GET :$GRAFANA_PORT/api/health -> $g1
datasource Prometheus: $g2
dashboards: $g3"

# ---------------------------------------------------------------- T-B09 Reverse proxy
r1=$(code "$P/")
r2=$(curl -s "$P/api/hello")
r3=$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' "$P/auth/")
[ "$r1" = 200 ] && [[ "$r2" == *"Hello from App Server!"* ]] && [[ "$r3" == 302*"/auth/admin/"* ]]
result T-B09 "Proxy: / -> web, /api/ -> app, /auth/ -> Keycloak" $? "GET :$PROXY_PORT/          -> $r1
GET :$PROXY_PORT/api/hello -> $r2
GET :$PROXY_PORT/auth/     -> $r3"

# ---------------------------------------------------------------- T-B10 Mạng cloud-net
pg=$(docker exec api-gateway-proxy-server sh -c '
  for h in web app-server db keycloak minio prometheus grafana dns-server node-exporter; do
    printf "%-14s " "$h"; ping -c 3 -q "$h" | grep "packet loss"
  done' 2>&1)
lost=$(printf '%s\n' "$pg" | grep -vc ' 0% packet loss')
[ "$lost" -eq 0 ]
result T-B10 "Mạng: ping 9 server từ trong proxy, không mất gói" $? "$pg"

echo
echo "==================== PHẦN MỞ RỘNG ===================="
echo

# ---------------------------------------------------------------- T-E01 Blog
e1=""
ok=0
for p in blog1 blog2 blog3; do
  page=$(curl -s "$P/blog/$p.html")
  img=$(printf '%s' "$page" | grep -o 'src="/assets/[^"]*"' | head -1 | cut -d'"' -f2)
  ci=$(code "$P$img")
  back=$(printf '%s' "$page" | grep -c 'href="/"')
  title=$(printf '%s' "$page" | grep -o '<h1>[^<]*</h1>' | sed 's/<[^>]*>//g')
  e1="$e1$p.html: \"$title\" | ảnh $img -> $ci | link về trang chủ: $back
"
  { [ "$ci" = 200 ] && [ "$back" -ge 1 ]; } || ok=1
done
links=$(curl -s "$P/" | grep -o 'href="/blog/blog[123].html"' | sort -u | wc -l)
[ "$ok" -eq 0 ] && [ "$links" -eq 3 ]
result T-E01 "Blog cá nhân: 3 bài có ảnh, link về trang chủ, trang chủ liệt kê đủ" $? "${e1}trang chủ có link tới $links/3 bài"

# ---------------------------------------------------------------- T-E02 /student (JSON)
s1=$(curl -s "$P/api/student")
s1n=$(printf '%s' "$s1" | json "sum(1 for x in d if {'id','name','major','gpa'} <= set(x))")
[ "$s1n" = 5 ]
result T-E02 "API /student đọc students.json qua proxy: 5 sinh viên đủ 4 trường" $? "GET :$PROXY_PORT/api/student -> $s1n bản ghi
$(printf '%s' "$s1" | json "'\n'.join(f\"{x['id']} | {x['name']} | {x['major']} | {x['gpa']}\" for x in d)")"

# ---------------------------------------------------------------- T-E03 studentdb
s3=$(docker exec relational-database-server sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e "SELECT COUNT(*) FROM studentdb.students"' 2>/dev/null)
s3a=$(curl -s "$P/api/students-db")
s3n=$(printf '%s' "$s3a" | json "len(d)")
[ "${s3:-0}" -ge 3 ] && [ "$s3n" = "$s3" ]
result T-E03 "studentdb.students có ≥3 bản ghi, API /students-db đọc đúng từ MariaDB" $? "SELECT COUNT(*) FROM studentdb.students -> $s3
GET :$PROXY_PORT/api/students-db -> $s3n bản ghi
$(printf '%s' "$s3a" | json "'\n'.join(f\"{x['student_id']} | {x['fullname']} | {x['dob']} | {x['major']}\" for x in d)")"

# ---------------------------------------------------------------- T-E04 Keycloak realm + /secure
TOKEN=$(curl -s -X POST "$P/auth/realms/$KC_REALM/protocol/openid-connect/token" \
          -d grant_type=password -d "client_id=$OIDC_CLIENT_ID" -d username=sv01 --data-urlencode "password=$SV_PASSWORD" \
        | json "d.get('access_token','')")
t1=$(curl -s -w ' [%{http_code}]' "$P/api/secure" -H "Authorization: Bearer $TOKEN")
t2=$(curl -s -w ' [%{http_code}]' "$P/api/secure")
t3=$(curl -s -w ' [%{http_code}]' "$P/api/secure" -H "Authorization: Bearer ${TOKEN%?????}AAAAA")
[[ "$t1" == *'"preferred_username":"sv01"'*'[200]' ]] && [[ "$t2" == *'[401]' ]] && [[ "$t3" == *'[401]' ]]
result T-E04 "Realm $KC_REALM: token sv01 gọi /secure được, không token/token sai bị chặn" $? "token hợp lệ  -> $t1
không token   -> $t2
token bị sửa  -> $t3"

# ---------------------------------------------------------------- T-E05 MinIO bucket policy
o1=$(code "http://$H:$MINIO_API_PORT/profile-pics/avatar.jpg")
o2=$(code "http://$H:$MINIO_API_PORT/documents/report.pdf")
psurl=$(docker run --rm --network cloud-net \
          -e MC_HOST_local="http://${MINIO_ROOT_USER}:${MINIO_ROOT_PASSWORD}@object-storage-server:9000" \
          pgsty/mc:RELEASE.2026-10-18T00-00-00Z share download --expire 10m local/documents/report.pdf 2>/dev/null \
        | grep -o 'http://[^ ]*X-Amz-Signature=[0-9a-f]*')
o3=$(docker run --rm --network cloud-net "$NETSHOOT" curl -s -o /dev/null -w '%{http_code}' "$psurl")
[ "$o1" = 200 ] && [ "$o2" = 403 ] && [ "$o3" = 200 ]
result T-E05 "MinIO: profile-pics public, documents private (chỉ mở được bằng URL có chữ ký)" $? "GET :$MINIO_API_PORT/profile-pics/avatar.jpg (ẩn danh)        -> $o1
GET :$MINIO_API_PORT/documents/report.pdf (ẩn danh)           -> $o2
GET documents/report.pdf bằng presigned URL (hết hạn 10 phút) -> $o3"

# ---------------------------------------------------------------- T-E06 DNS records mới
e6=""
ok=0
for pair in app-backend:10.10.10.20 minio:10.10.10.50 keycloak:10.10.10.40; do
  name=${pair%%:*}; want=${pair#*:}
  got=$(dig_host "$name.cloud.local" +short +time=3 2>&1)
  e6="$e6$name.cloud.local -> $got (cần $want)
"
  [ "$got" = "$want" ] || ok=1
done
[ "$ok" -eq 0 ]
result T-E06 "DNS: thêm app-backend, minio, keycloak vào zone cloud.local" $? "${e6%?}"

# ---------------------------------------------------------------- T-E07 Prometheus job web
w7=$(curl -s "http://$H:$PROM_PORT/api/v1/targets" \
      | json "' '.join(t['scrapeUrl']+' '+t['health'] for t in d['data']['activeTargets'] if t['labels']['job']=='web')")
w7m=$(curl -s "http://$H:$PROM_PORT/api/v1/query?query=nginx_up" | json "d['data']['result'][0]['value'][1] if d['data']['result'] else 'none'")
[[ "$w7" == *" up" ]] && [ "$w7m" = 1 ]
result T-E07 "Prometheus: job 'web' giám sát web-frontend-server UP" $? "job web: $w7
nginx_up = $w7m"

# ---------------------------------------------------------------- T-E08 Grafana dashboard
g8=$(curl -s -u "$GF_ADMIN_USER:$GF_ADMIN_PASSWORD" "http://$H:$GRAFANA_PORT/api/dashboards/uid/system-health-523h0008-523h0025" \
      | json "d['dashboard']['title'] + ' | ' + ', '.join(p['title'] for p in d['dashboard']['panels'])")
[[ "$g8" == "System Health of 523H0008 & 523H0025 | CPU Usage (%), Memory Usage, Network Traffic"* ]]
result T-E08 "Grafana: dashboard System Health có biểu đồ CPU, Memory, Network" $? "$g8"

# ---------------------------------------------------------------- T-E09 /student/ qua proxy
r9=$(curl -s "$P/student/")
r9n=$(printf '%s' "$r9" | json "len(d)")
[ "$r9" = "$s1" ] && [ "$r9n" = 5 ]
result T-E09 "Proxy: /student/ trả danh sách sinh viên từ backend" $? "GET :$PROXY_PORT/student/ -> $r9n bản ghi, giống /api/student"

# ---------------------------------------------------------------- T-E10 Load balancing
lb=$(for i in 1 2 3 4 5 6; do curl -s -D - -o /dev/null "$P/" | tr -d '\r' | awk 'tolower($1)=="x-served-by:"{print $2}'; done | tr '\n' ' ')
n1=$(printf '%s' "$lb" | grep -o web1 | wc -l)
n2=$(printf '%s' "$lb" | grep -o web2 | wc -l)
[ "$n1" -eq 3 ] && [ "$n2" -eq 3 ]
result T-E10 "Load balancing round robin: 6 request chia đều web1/web2" $? "X-Served-By: $lb
(kiểm thử failover đầy đủ: bash scripts/lb-test.sh)"

# Phần nâng cao ngoài đề
. scripts/smoke-advanced.sh

echo
echo "Tổng kết: $pass PASS, $fail FAIL"
[ "$fail" -eq 0 ]
