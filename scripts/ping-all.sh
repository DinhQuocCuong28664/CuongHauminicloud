#!/usr/bin/env bash
# ping-all.sh — demo item 10 of the assignment: from inside the proxy container, ping the other servers
# in cloud-net by name (alias) and print the full output. Saved to evidence/ping-all.txt
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
