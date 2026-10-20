# smoke-advanced.sh — các test case phần nâng cao (T-A01…T-A11), được smoke-test.sh "source" sau phần đề bài.
# Dùng lại biến và hàm của smoke-test.sh: P (URL gateway), H, PY, result, code, json, NETSHOOT.
# Đặt SKIP_ALERT_TEST=1 để bỏ qua T-A07 (dừng web2 khoảng 2 phút để chờ cảnh báo firing rồi resolved).

echo
echo "===================================================== Phần nâng cao (ngoài đề)"

token() {
  curl -s -X POST "$P/auth/realms/$KC_REALM/protocol/openid-connect/token" -d grant_type=password \
    -d "client_id=$OIDC_CLIENT_ID" -d "username=$1" --data-urlencode "password=$SV_PASSWORD" | json "d.get('access_token','')"
}
claim() { printf '%s' "$1" | $PY -c "
import sys, json, base64
p = sys.stdin.read().split('.')[1]; p += '=' * (-len(p) % 4)
d = json.loads(base64.urlsafe_b64decode(p)); print($2)"; }
T1=$(token sv01)
T2=$(token sv02)
A1="Authorization: Bearer $T1"
A2="Authorization: Bearer $T2"
loki() {   # loki <LogQL>  -> số dòng log khớp trong 10 phút gần nhất
  docker run --rm --network cloud-net "$NETSHOOT" curl -s -G http://logging-loki-server:3100/loki/api/v1/query_range \
    --data-urlencode "query=$1" --data-urlencode "since=10m" --data-urlencode "limit=100" \
    | json "sum(len(s['values']) for s in d['data']['result'])"
}
prom() { curl -s "http://$H:$PROM_PORT/api/v1/query" --data-urlencode "query=$1" | json "d['data']['result'][0]['value'][1] if d['data']['result'] else 'none'"; }

# ---------------------------------------------------------------- T-A01 Portal + PKCE
p1=$(code "$P/portal/")
p1h=$(curl -s -D - -o /dev/null "$P/portal/" | tr -d '\r' | awk -F': ' 'tolower($1)=="content-security-policy"{print $2}')
p1t=$(curl -s "$P/portal/" | grep -o '<title>[^<]*</title>')
AUTH="$P/auth/realms/$KC_REALM/protocol/openid-connect/auth?client_id=portal&response_type=code&scope=openid&redirect_uri=$(printf '%s' "$P/portal/" | sed 's/:/%3A/g; s#/#%2F#g')"
p1a=$(code "$AUTH&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&code_challenge_method=S256")
p1b=$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' "$AUTH" | sed 's/&.*//; s/?.*error=/ error=/')
p1c=$(curl -s -X POST "$P/auth/realms/$KC_REALM/protocol/openid-connect/token" -d grant_type=password -d client_id=portal \
       -d username=sv01 --data-urlencode "password=$SV_PASSWORD" | json "d.get('error')")
[ "$p1" = 200 ] && [[ "$p1t" == *Portal* ]] && [[ "$p1h" == *"default-src 'self'"* ]] && [ "$p1a" = 200 ] \
  && [[ "$p1b" == *invalid_request* || "$p1b" == 400* ]] && [ "$p1c" = unauthorized_client ]
result T-A01 "Portal: trang /portal/ có CSP; client portal bắt buộc PKCE, không cho đăng nhập bằng mật khẩu" $? "GET /portal/ -> $p1 $p1t
Content-Security-Policy: $p1h
auth có code_challenge S256 -> $p1a (trang đăng nhập)
auth thiếu code_challenge   -> $p1b
token grant_type=password, client portal -> $p1c"

# ---------------------------------------------------------------- T-A02 RBAC
r1=$(claim "$T1" "' '.join(r for r in d['realm_access']['roles'] if r in ('editor','viewer'))")
r2=$(claim "$T2" "' '.join(r for r in d['realm_access']['roles'] if r in ('editor','viewer'))")
a2a=$(code "$P/api/students")
a2b=$(code -H "$A2" "$P/api/students")
a2c=$(curl -s -o /dev/null -w '%{http_code}' -H "$A2" -H 'Content-Type: application/json' -d '{"student_id":"SV990","fullname":"Viewer"}' "$P/api/students")
a2d=$(code -H "$A2" "$P/api/documents")
[ "$a2a" = 401 ] && [ "$a2b" = 200 ] && [ "$a2c" = 403 ] && [ "$a2d" = 403 ] && [[ "$r1" == *editor* ]] && [ "$r2" = viewer ]
result T-A02 "RBAC: sv01 (editor) được ghi, sv02 (viewer) chỉ đọc, không token bị chặn" $? "role trong token: sv01=[$r1] sv02=[$r2]
GET  /api/students không token -> $a2a
GET  /api/students sv02        -> $a2b
POST /api/students sv02        -> $a2c
GET  /api/documents sv02       -> $a2d"

# ---------------------------------------------------------------- T-A03 CRUD
c_new=$(curl -s -w '\n%{http_code}' -H "$A1" -H 'Content-Type: application/json' \
         -d '{"student_id":"SV990","fullname":"Smoke Test","dob":"2005-05-05","major":"Cloud"}' "$P/api/students")
c_id=$(printf '%s' "$c_new" | head -1 | json "d.get('id')")
c1=$(printf '%s' "$c_new" | tail -1)
c2=$(curl -s -o /dev/null -w '%{http_code}' -X PUT -H "$A1" -H 'Content-Type: application/json' \
      -d '{"student_id":"SV990","fullname":"Smoke Test","dob":"2005-05-05","major":"DevOps"}' "$P/api/students/$c_id")
c2m=$(curl -s -H "$A1" "$P/api/students" | json "next(s['major'] for s in d['students'] if s['id']==$c_id)")
c3=$(curl -s -o /dev/null -w '%{http_code}' -H "$A1" -H 'Content-Type: application/json' -d '{"student_id":"!","fullname":""}' "$P/api/students")
c4=$(code -X DELETE -H "$A1" "$P/api/students/$c_id")
c5=$(code -X DELETE -H "$A1" "$P/api/students/$c_id")
[ "$c1" = 201 ] && [ "$c2" = 200 ] && [ "$c2m" = DevOps ] && [ "$c3" = 400 ] && [ "$c4" = 204 ] && [ "$c5" = 404 ]
result T-A03 "CRUD /api/students trên MariaDB: thêm 201, sửa 200, dữ liệu sai 400, xoá 204, xoá lại 404" $? "POST   /api/students           -> $c1 (id $c_id)
PUT    /api/students/$c_id        -> $c2 (major = $c2m)
POST   dữ liệu sai             -> $c3
DELETE /api/students/$c_id        -> $c4
DELETE lần hai                 -> $c5"

# ---------------------------------------------------------------- T-A04 Ảnh đại diện và tài liệu private
o1=$(curl -s -H "$A1" -F "file=@object-storage-server/samples/avatar.jpg" "$P/api/avatar")
o1u=$(printf '%s' "$o1" | json "d.get('url','')")
o2=$(curl -s -o /dev/null -w '%{http_code} %{content_type}' "$P${o1u}")
o3=$(curl -s -o /dev/null -w '%{http_code}' -H "$A1" -F "file=@README.md" "$P/api/avatar")
# Ghi ra file tạm trong thư mục dự án: curl của Git Bash là bản Windows (mingw), báo 0 byte khi ghi vào
# /dev/null và không hiểu đường dẫn /tmp/... khi MSYS_NO_PATHCONV=1
o4f=logs/.a04-download.tmp
o4=$(curl -s -o "$o4f" -w '%{http_code}' -H "$A1" "$P/api/documents/report.pdf")
o4="$o4 $(wc -c < "$o4f" | tr -d ' ')"; rm -f "$o4f"
o5=$(code "$P/api/documents/report.pdf")
o6=$(code -X PUT -d x "$P/media/hack.jpg")
o7=$(code "http://$H:$MINIO_API_PORT/documents/report.pdf")
[[ "$o2" == "200 image/jpeg" ]] && [ "$o3" = 415 ] && [[ "$o4" == 200\ * ]] && [ "${o4#* }" -gt 100000 ] \
  && [ "$o5" = 401 ] && [ "$o6" = 403 ] && [ "$o7" = 403 ]
result T-A04 "MinIO qua app: upload ảnh vào profile-pics, đọc qua /media/; documents chỉ editor tải được" $? "POST /api/avatar (sv01)        -> $o1
GET  $o1u -> $o2
POST /api/avatar file không phải ảnh -> $o3
GET  /api/documents/report.pdf sv01      -> $o4 byte
GET  /api/documents/report.pdf không token -> $o5
PUT  /media/hack.jpg                     -> $o6
GET  :$MINIO_API_PORT/documents/report.pdf ẩn danh -> $o7"

# ---------------------------------------------------------------- T-A05 Log tập trung (Loki)
rid=$(curl -s -D - -o /dev/null "$P/api/students-db" | tr -d '\r' | awk -F': ' 'tolower($1)=="x-request-id"{print $2}')
l1=0; l2=0
for i in $(seq 1 12); do
  sleep 5
  l1=$(loki "{service=\"api-gateway-proxy-server\"} |= \"$rid\"")
  l2=$(loki "{service=\"application-backend-server\"} |= \"$rid\"")
  [ "$l1" -ge 1 ] && [ "$l2" -ge 1 ] && break
done
l3=$(docker run --rm --network cloud-net "$NETSHOOT" curl -s http://logging-loki-server:3100/loki/api/v1/label/container/values | json "len(d['data'])")
[ "$l1" -ge 1 ] && [ "$l2" -ge 1 ] && [ "$l3" -ge 14 ]
result T-A05 "Loki: log mọi container; một request_id tra được ở cả proxy và app" $? "X-Request-ID của GET /api/students-db: $rid
dòng log ở proxy: $l1, ở app: $l2 (sau $((i * 5)) s)
số container có log trong Loki: $l3"

# ---------------------------------------------------------------- T-A06 Giám sát container và API
m1=$(curl -s "http://$H:$PROM_PORT/api/v1/targets" | json "' '.join(t['labels']['job']+'='+t['health'] for t in d['data']['activeTargets'] if t['labels']['job'] in ('cadvisor','app','alertmanager','loki'))")
m2=$(prom 'count(container_last_seen{container_label_com_docker_compose_project="cuonghauminicloud"})')
m3=$(prom 'sum(minicloud_http_requests_total)')
m4=$(prom 'histogram_quantile(0.95, sum by (le) (rate(minicloud_http_request_duration_seconds_bucket[5m])))')
m5=$(curl -s -u "$GF_ADMIN_USER:$GF_ADMIN_PASSWORD" "http://$H:$GRAFANA_PORT/api/search?tag=nang-cao" | json "len(d)")
[[ "$m1" != *down* ]] && [[ "$m1" == *cadvisor=up* ]] && [[ "$m1" == *app=up* ]] && [ "${m2:-0}" -ge 16 ] \
  && [ "${m3%.*}" -gt 0 ] && [ "$m5" -ge 4 ]
result T-A06 "cAdvisor theo dõi từng container, app xuất metric RED, Grafana có 4 dashboard nâng cao" $? "target: $m1
container được cAdvisor theo dõi: $m2
tổng request API đã đếm: $m3, p95 5 phút: $m4 s
dashboard tag nang-cao: $m5"

# ---------------------------------------------------------------- T-A07 Cảnh báo: dừng web2 -> firing -> resolved
alert_state() { curl -s -H "$A1" "$P/api/alerts" | json "next((a['status'] for a in d['alerts'] if a['alertname']=='WebServerDown'), 'none')"; }
w_rules=$(curl -s "http://$H:$PROM_PORT/api/v1/rules" | json "sum(len(g['rules']) for g in d['data']['groups'])")
if [ "${SKIP_ALERT_TEST:-0}" = 1 ]; then
  echo "[SKIP] T-A07  Cảnh báo (SKIP_ALERT_TEST=1); số luật cảnh báo: $w_rules"
else
  T1=$(token sv01); A1="Authorization: Bearer $T1"
  docker stop web-frontend-server2 >/dev/null
  t0=$(date +%s); f=none
  while [ $(( $(date +%s) - t0 )) -lt 150 ]; do f=$(alert_state); [ "$f" = firing ] && break; sleep 5; done
  tf=$(( $(date +%s) - t0 ))
  lbw=$(for i in 1 2 3 4; do code "$P/"; printf ' '; done)
  docker start web-frontend-server2 >/dev/null
  t1=$(date +%s); r=$f
  while [ $(( $(date +%s) - t1 )) -lt 150 ]; do r=$(alert_state); [ "$r" = resolved ] && break; sleep 5; done
  tr_=$(( $(date +%s) - t1 ))
  [ "$f" = firing ] && [ "$r" = resolved ] && [ "$w_rules" -ge 6 ]
  result T-A07 "Cảnh báo: dừng web2 -> WebServerDown firing, gửi tới app; bật lại -> resolved" $? "số luật cảnh báo đã nạp: $w_rules
docker stop web-frontend-server2 -> app nhận firing sau ${tf} s; trong lúc đó GET / qua proxy: $lbw
docker start web-frontend-server2 -> app nhận resolved sau ${tr_} s"
fi

# ---------------------------------------------------------------- T-A08 Gateway: rate limit, header, HTTPS
g1=$(for i in $(seq 1 40); do code "$P/api/hello"; echo; done | sort | uniq -c | awk '{printf "%s×%s ", $2, $1}')
sleep 3
g2=$(curl -s -D - -o /dev/null "$P/api/hello" | tr -d '\r' | awk -F': ' 'tolower($1) ~ /^(x-content-type-options|x-frame-options|x-request-id|referrer-policy|strict-transport-security)$/ {printf "%s ", $1}')
g3=$(code "$P/api/metrics")
g4=$(code -X POST "$P/api/alerts")
tls_ok=0; tls_info="(chạy HTTP, không kiểm tra HTTPS)"
if [[ "$P" == https://* ]]; then
  dom=${P#https://}
  g5=$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' "http://$dom/portal/")
  g6=$(echo | openssl s_client -connect "$dom:443" -servername "$dom" 2>/dev/null | openssl x509 -noout -issuer -enddate 2>/dev/null | tr '\n' ' ')
  g7=$(claim "$T1" "d['iss']")
  [[ "$g5" == "301 https://$dom/portal/" ]] && [[ "$g6" == *"Let's Encrypt"* ]] && [[ "$g7" == https://* ]] && [[ "$g2" == *strict-transport-security* || "$g2" == *Strict-Transport-Security* ]] || tls_ok=1
  tls_info="http://$dom/portal/ -> $g5
chứng chỉ: $g6
issuer của token: $g7"
fi
[[ "$g1" == *429* ]] && [[ "$g1" == *200* ]] && [ "$g3" = 404 ] && [ "$g4" = 403 ] && [ "$tls_ok" = 0 ] \
  && [[ "${g2,,}" == *x-request-id* ]] && [[ "${g2,,}" == *x-content-type-options* ]]
result T-A08 "Gateway: rate limit 429, header bảo mật, chặn /api/metrics và POST /api/alerts, HTTPS khi chạy EC2" $? "40 request liên tiếp /api/hello -> $g1
header: $g2
GET /api/metrics -> $g3, POST /api/alerts -> $g4
$tls_info"

# ---------------------------------------------------------------- T-A09 Sao lưu và khôi phục
b1=$(docker compose --profile ops run --rm db-backup 2>/dev/null); b1c=$?
b2=$(docker compose --profile ops run --rm --entrypoint python db-backup /app/restore.py 2>/dev/null); b2c=$?
[ "$b1c" = 0 ] && [ "$b2c" = 0 ] && [[ "$b2" == *"khôi phục đúng"* ]] && [[ "$b1" == *"xoá sau 7 ngày"* ]]
result T-A09 "Sao lưu MariaDB sang MinIO (db-backups, lifecycle 7 ngày) và khôi phục thử khớp bản gốc" $? "$(printf '%s\n' "$b1" | grep -E 'sql.gz +dump|Lifecycle')
$(printf '%s\n' "$b2" | grep -E 'sha256|students|KẾT LUẬN')"

# ---------------------------------------------------------------- T-A10 Service discovery qua DNS nội bộ
d1=$(docker exec application-backend-server getent hosts db.cloud.local | awk '{print $1}')
d2=$(docker exec application-backend-server getent hosts s3.cloud.local | awk '{print $1, $2}')
d3=$(docker exec application-backend-server printenv DB_HOST S3_ENDPOINT | tr '\n' ' ')
d4=$(code "$P/api/notes")
[ "$d1" = 10.10.10.30 ] && [[ "$d2" == 10.10.10.50* ]] && [ "$d4" = 200 ]
result T-A10 "DNS nội bộ: app kết nối DB, MinIO bằng tên cloud.local do BIND9 phân giải" $? "app: DB_HOST, S3_ENDPOINT = $d3
getent hosts db.cloud.local -> $d1
getent hosts s3.cloud.local -> $d2 (CNAME)
GET /api/notes (đọc DB qua db.cloud.local) -> $d4"

# ---------------------------------------------------------------- T-A11 Compose hardening
# Chờ tối đa 60 giây cho container vừa khởi động lại (web2 ở T-A07) qua healthcheck
for i in $(seq 1 12); do
  h1=$(docker compose ps --format '{{.Name}} {{.Status}}' | grep -c '(healthy)')
  [ "$h1" -ge 14 ] && break; sleep 5
done
h2=$(docker compose ps -q | xargs docker inspect --format '{{.HostConfig.Memory}}' | grep -vc '^0$')
h3=$(docker compose ps -q | xargs docker inspect --format '{{.HostConfig.SecurityOpt}}' | grep -c 'no-new-privileges')
h4=$(docker compose ps -q | wc -l)
[ "$h1" -ge 14 ] && [ "$h2" = "$h4" ] && [ "$h3" = "$h4" ]
result T-A11 "Compose: mọi container có giới hạn RAM, no-new-privileges; 14 container có healthcheck đều healthy" $? "container đang chạy: $h4
có giới hạn RAM: $h2, có no-new-privileges: $h3, healthy: $h1 (Loki, nginx-exporter là image distroless, không có healthcheck)"
