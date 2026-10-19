#!/usr/bin/env bash
# ping-all.sh — mục 10 phần demo của đề: đứng trong container proxy, ping các server khác
# trong cloud-net bằng tên (alias), in toàn bộ kết quả. Lưu vào evidence/ping-all.txt
set -u
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
mkdir -p evidence

docker exec api-gateway-proxy-server sh -c '
  for h in web app-server db keycloak minio prometheus grafana dns-server node-exporter; do
    echo "# ping -c 3 $h"
    ping -c 3 "$h"
    echo
  done' 2>&1 | tee evidence/ping-all.txt
