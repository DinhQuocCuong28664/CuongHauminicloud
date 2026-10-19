#!/usr/bin/env bash
# lb-test.sh — mở rộng 10: kiểm chứng proxy cân bằng tải round robin giữa web-frontend-server1 và 2,
# và khả năng chịu lỗi khi một web server dừng.
#   bash scripts/lb-test.sh          Kết quả ghi vào evidence/e10-lb-test.txt
set -u
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
H=${SMOKE_HOST:-localhost}
URL="http://$H:$PROXY_PORT/"
mkdir -p evidence

# In mỗi request một dòng: mã HTTP, thời gian, web server đã phục vụ, upstream proxy đã thử
hit() {
  for i in $(seq 1 "$1"); do
    curl -s -D - -o /dev/null -w 'time: %{time_total}\n' "$URL" | tr -d '\r' | awk -v n="$i" '
      /^HTTP/                      { code = $2 }
      tolower($1) == "x-served-by:" { served = $2 }
      tolower($1) == "x-upstream-addr:" { $1 = ""; upstream = substr($0, 2) }
      /^time:/                     { t = $2 }
      END { printf "  request %-2s HTTP %s  %6.3fs  served-by=%-5s upstream=%s\n", n, code, t, served, upstream }'
  done
}

{
echo "### 1. Round robin: 6 request liên tiếp tới $URL"
hit 6
echo
echo "### 2. Dừng web-frontend-server2 (giả lập một server hỏng)"
docker stop web-frontend-server2
hit 4
echo
echo "### 3. Bật lại web-frontend-server2"
docker start web-frontend-server2
echo "  (chờ 6 giây cho hết fail_timeout=5s để proxy thử lại web2)"
sleep 6
hit 6
echo
echo "### Log của proxy (upstream đã phục vụ từng request)"
docker logs --tail 40 api-gateway-proxy-server 2>/dev/null | grep 'GET / ' | tail -16
} 2>&1 | tee evidence/e10-lb-test.txt
