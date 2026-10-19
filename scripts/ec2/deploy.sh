#!/usr/bin/env bash
# deploy.sh — đưa MyMiniCloud lên EC2 đã tạo bằng launch.sh:
#   1. chờ cloud-init cài xong Docker
#   2. gửi mã nguồn (file được git theo dõi + report.pdf mẫu) và .env của EC2 (PUBLIC_HOST = public IP,
#      cổng theo đúng đề: web 8080, DB 3306)
#   3. docker compose pull (3 image tự build lấy từ Docker Hub) rồi up -d --no-build
#   4. tắt "HTTPS required" của realm master, chạy smoke test trên EC2, lấy log và minh chứng về máy
#   bash scripts/ec2/deploy.sh
set -euo pipefail
export MSYS_NO_PATHCONV=1
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
. scripts/ec2/instance.env

SSH_OPTS=(-i "scripts/ec2/$KEY_FILE" -o StrictHostKeyChecking=accept-new
          -o UserKnownHostsFile=scripts/ec2/known_hosts -o ConnectTimeout=10 -o LogLevel=ERROR)
ssh_() { ssh "${SSH_OPTS[@]}" "ubuntu@$PUBLIC_IP" "$@"; }
scp_() { scp "${SSH_OPTS[@]}" "$@"; }
REMOTE_DIR=CuongHauminicloud
mkdir -p evidence logs

echo "== 1. Chờ cloud-init cài Docker trên $PUBLIC_IP"
for i in $(seq 1 60); do
  ssh_ 'test -f /var/log/minicloud-user-data.done' 2>/dev/null && break
  [ "$i" -eq 60 ] && { echo "Quá thời gian chờ cloud-init"; exit 1; }
  sleep 10
done
ssh_ 'docker --version && docker compose version && free -h | head -3'

echo "== 2. Gửi mã nguồn và .env"
TMP=$(mktemp -d)
{ git ls-files -co --exclude-standard | grep -vE '^(evidence|logs)/|^scripts/ec2/'
  [ -f object-storage-server/samples/report.pdf ] && echo object-storage-server/samples/report.pdf
} | tar -czf "$TMP/minicloud.tar.gz" -T -
sed -e "s/^PUBLIC_HOST=.*/PUBLIC_HOST=$PUBLIC_IP/" \
    -e 's/^WEB1_PORT=.*/WEB1_PORT=8080/' -e 's/^DB_PORT=.*/DB_PORT=3306/' \
    -e '/^# WEB1_PORT\/DB_PORT local/d' -e 's/^# File .env local.*/# File .env trên EC2 (tạo bởi deploy.sh)/' \
    .env > "$TMP/env.ec2"
scp_ "$TMP/minicloud.tar.gz" "$TMP/env.ec2" "ubuntu@$PUBLIC_IP:~/"
rm -rf "$TMP"
ssh_ "mkdir -p $REMOTE_DIR && tar -xzf minicloud.tar.gz -C $REMOTE_DIR && mv env.ec2 $REMOTE_DIR/.env && chmod 600 $REMOTE_DIR/.env && rm minicloud.tar.gz"

echo "== 3. docker compose pull + up"
ssh_ "cd $REMOTE_DIR && docker compose pull 2>&1 | grep -E 'Pulled|pull' | tail -15 && docker compose up -d --no-build 2>&1 | tail -3"
for i in $(seq 1 60); do
  st=$(ssh_ "docker inspect -f '{{.State.Health.Status}}' authentication-identity-server" 2>/dev/null || true)
  [ "$st" = healthy ] && break
  sleep 5
done
echo "Keycloak: $st"

echo "== 4. Hậu kiểm và smoke test trên EC2"
ssh_ "cd $REMOTE_DIR && bash authentication-identity-server/post-start.sh"
ssh_ "cd $REMOTE_DIR && bash scripts/smoke-test.sh ec2 >/dev/null 2>&1; tail -1 logs/smoke-ec2.txt" || true
scp_ "ubuntu@$PUBLIC_IP:~/$REMOTE_DIR/logs/smoke-ec2.txt" logs/smoke-ec2.txt

{
  echo "\$ ssh -i $KEY_FILE ubuntu@$PUBLIC_IP"
  ssh_ "echo \"\$(whoami)@\$(hostname)\"; grep PRETTY_NAME /etc/os-release; uname -r; nproc; free -h | head -2"
  echo
  echo "\$ docker compose ps"
  ssh_ "cd $REMOTE_DIR && docker compose ps --format 'table {{.Name}}\t{{.Image}}\t{{.Status}}'"
} | tr -d '\r' > evidence/ec2-compose-ps.txt
ssh_ "docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'; echo; free -h" | tr -d '\r' > evidence/ec2-docker-stats.txt
ssh_ "docker images --format 'table {{.Repository}}:{{.Tag}}\t{{.ID}}\t{{.Size}}' | grep -E 'REPOSITORY|dinhquoccuong286'" | tr -d '\r' > evidence/ec2-dockerhub-images.txt
cat evidence/ec2-compose-ps.txt
echo
grep -E '^\[(PASS|FAIL)\]|Tổng kết' logs/smoke-ec2.txt
