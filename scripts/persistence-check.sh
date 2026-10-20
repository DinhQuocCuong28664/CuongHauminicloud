#!/usr/bin/env bash
# persistence-check.sh — verify that volume data survives removing and recreating the containers:
# record the state, run "docker compose down" (no -v) then "up -d", record the state again and compare.
#   bash scripts/persistence-check.sh         Results go to evidence/persistence-check.txt
set -u
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
if python3 -c 'pass' >/dev/null 2>&1; then PY=python3; else PY=python; fi
mkdir -p evidence

snapshot() {
  echo "  MariaDB  studentdb.students: $(docker exec relational-database-server sh -c \
    'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e "SELECT COUNT(*) FROM studentdb.students"' 2>/dev/null) bản ghi"
  echo "  MinIO    objects: $(docker run --rm --network cloud-net \
    -e MC_HOST_local="http://${MINIO_ROOT_USER}:${MINIO_ROOT_PASSWORD}@object-storage-server:9000" \
    pgsty/mc:RELEASE.2026-10-18T00-00-00Z ls --recursive local 2>/dev/null | awk '{print $NF}' | tr '\n' ' ')"
  adm=$(curl -s -X POST "http://localhost:$AUTH_PORT/auth/realms/master/protocol/openid-connect/token" \
          -d grant_type=password -d client_id=admin-cli -d "username=$KC_ADMIN" --data-urlencode "password=$KC_ADMIN_PASSWORD" \
        | $PY -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
  echo "  Keycloak user sv-test (master): $(curl -s "http://localhost:$AUTH_PORT/auth/admin/realms/master/users?username=sv-test&exact=true" \
    -H "Authorization: Bearer $adm" | $PY -c "import sys,json; print(len(json.load(sys.stdin)))") user"
  echo "  Grafana  dashboards: $(curl -s -u "$GF_ADMIN_USER:$GF_ADMIN_PASSWORD" "http://localhost:$GRAFANA_PORT/api/search?type=dash-db" \
    | $PY -c "import sys,json; print(', '.join(x['title'] for x in json.load(sys.stdin)))")"
  echo "  Prometheus mẫu up{job=\"node\"} trong 10 phút qua: $(curl -s --get "http://localhost:$PROM_PORT/api/v1/query" \
    --data-urlencode 'query=count_over_time(up{job="node"}[10m])' \
    | $PY -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(r[0]['value'][1] if r else 0)") (scrape 15 giây/lần)"
}

wait_healthy() {
  for _ in $(seq 1 60); do
    [ "$(docker inspect -f '{{.State.Health.Status}}' authentication-identity-server 2>/dev/null)" = healthy ] \
      && [ "$(docker inspect -f '{{.State.Running}}' api-gateway-proxy-server 2>/dev/null)" = true ] && return 0
    sleep 3
  done
  return 1
}

{
echo "### Trước khi xoá container ($(date '+%H:%M:%S'))"
snapshot
echo
echo "\$ docker compose down        (xoá container và network, GIỮ volume)"
docker compose down 2>&1 | grep -c Removed | xargs -I{} echo "  {} đối tượng đã xoá"
echo "\$ docker compose up -d"
docker compose up -d >/dev/null 2>&1
wait_healthy && echo "  cụm đã chạy lại, Keycloak healthy"
sleep 15
echo
echo "### Sau khi tạo lại container ($(date '+%H:%M:%S'))"
snapshot
} 2>&1 | tee evidence/persistence-check.txt
