#!/usr/bin/env bash
# deploy.sh — đưa MyMiniCloud lên EC2 đã tạo bằng launch.sh, có HTTPS:
#   1. chờ cloud-init cài xong Docker
#   2. gửi mã nguồn (file được git theo dõi + report.pdf mẫu) và .env của EC2
#      (PUBLIC_HOST = public IP, PUBLIC_DOMAIN = <ip-dạng-gạch>.sslip.io, cổng theo đúng đề: web 8080, DB 3306)
#   3. docker compose pull (image tự build lấy từ Docker Hub) rồi up -d bản HTTP
#   4. xin chứng chỉ Let's Encrypt cho PUBLIC_DOMAIN (xác thực HTTP-01 qua thư mục webroot của proxy),
#      rồi chạy lại với docker-compose.ec2.yml: proxy nghe 443, cổng 80 chuyển sang HTTPS, Keycloak dùng issuer https
#   5. cập nhật dữ liệu của bản cũ: realm (role, client portal), database ops, user/bucket MinIO; đặt cron sao lưu
#      và gia hạn chứng chỉ
#   6. smoke test trên EC2, lấy log và minh chứng về máy
#   bash scripts/ec2/deploy.sh
set -euo pipefail
export MSYS_NO_PATHCONV=1
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
. scripts/ec2/instance.env

DOMAIN="$(printf '%s' "$PUBLIC_IP" | tr . -).sslip.io"
SSH_OPTS=(-i "scripts/ec2/$KEY_FILE" -o StrictHostKeyChecking=accept-new
          -o UserKnownHostsFile=scripts/ec2/known_hosts -o ConnectTimeout=10 -o LogLevel=ERROR)
ssh_() { ssh "${SSH_OPTS[@]}" "ubuntu@$PUBLIC_IP" "$@"; }
scp_() { scp "${SSH_OPTS[@]}" "$@"; }
REMOTE_DIR=CuongHauminicloud
DC="docker compose -f docker-compose.yml -f docker-compose.ec2.yml"
mkdir -p evidence logs
wait_healthy() {   # wait_healthy <container>
  for i in $(seq 1 90); do
    st=$(ssh_ "docker inspect -f '{{.State.Health.Status}}' $1" 2>/dev/null || true)
    [ "$st" = healthy ] && break
    sleep 5
  done
  echo "  $1: $st"
}

echo "== 1. Chờ cloud-init cài Docker trên $PUBLIC_IP"
for i in $(seq 1 60); do
  ssh_ 'test -f /var/log/minicloud-user-data.done' 2>/dev/null && break
  [ "$i" -eq 60 ] && { echo "Quá thời gian chờ cloud-init"; exit 1; }
  sleep 10
done
ssh_ 'docker --version && docker compose version && free -h | head -3'

echo "== 2. Gửi mã nguồn và .env (tên miền $DOMAIN)"
TMP=$(mktemp -d)
# Bỏ minh chứng, log, khoá SSH, kết quả k6 và tài liệu tham khảo của nhóm (không cần trên máy chủ)
{ git -c core.quotepath=off ls-files -co --exclude-standard \
    | grep -vE '^(evidence|logs)/|^scripts/ec2/|^scripts/loadtest/out/|guild_from_teacher/|\.docx"?$'
  [ -f object-storage-server/samples/report.pdf ] && echo object-storage-server/samples/report.pdf
} | tar -czf "$TMP/minicloud.tar.gz" -T -
sed -e "s/^PUBLIC_HOST=.*/PUBLIC_HOST=$PUBLIC_IP/" -e "s/^PUBLIC_DOMAIN=.*/PUBLIC_DOMAIN=$DOMAIN/" \
    -e 's/^WEB1_PORT=.*/WEB1_PORT=8080/' -e 's/^DB_PORT=.*/DB_PORT=3306/' \
    -e '/^# WEB1_PORT\/DB_PORT local/d' -e 's/^# File .env local.*/# File .env trên EC2 (tạo bởi deploy.sh)/' \
    .env > "$TMP/env.ec2"
scp_ "$TMP/minicloud.tar.gz" "$TMP/env.ec2" "ubuntu@$PUBLIC_IP:~/"
rm -rf "$TMP"
ssh_ "mkdir -p $REMOTE_DIR && tar -xzf minicloud.tar.gz -C $REMOTE_DIR && mv env.ec2 $REMOTE_DIR/.env && chmod 600 $REMOTE_DIR/.env && rm minicloud.tar.gz"

echo "== 3. docker compose pull + up (HTTP)"
ssh_ "cd $REMOTE_DIR && $DC --profile ops --profile tls pull -q 2>&1 | tail -3; docker compose up -d --no-build 2>&1 | tail -3"
wait_healthy api-gateway-proxy-server

echo "== 4. Chứng chỉ Let's Encrypt cho $DOMAIN, chuyển sang HTTPS"
if ssh_ "cd $REMOTE_DIR && $DC --profile tls run --rm certbot certificates 2>/dev/null | grep -q 'Domains: $DOMAIN'"; then
  echo "  đã có chứng chỉ cho $DOMAIN"
else
  # Không gửi email cho Let's Encrypt; --agree-tos: đồng ý điều khoản thuê bao của Let's Encrypt
  ssh_ "cd $REMOTE_DIR && $DC --profile tls run --rm certbot certonly --webroot -w /var/www/certbot -d $DOMAIN \
        --agree-tos --register-unsafely-without-email --non-interactive 2>&1 | tail -6"
fi
ssh_ "cd $REMOTE_DIR && $DC up -d --no-build 2>&1 | tail -4"
wait_healthy authentication-identity-server
wait_healthy api-gateway-proxy-server

echo "== 5. Cập nhật dữ liệu từ bản cũ, cron sao lưu và gia hạn chứng chỉ"
ssh_ "cd $REMOTE_DIR && bash authentication-identity-server/post-start.sh EXTERNAL"
ssh_ "cd $REMOTE_DIR && bash authentication-identity-server/sync-realm.sh"
ssh_ "cd $REMOTE_DIR && bash scripts/db-migrate.sh"
ssh_ "cd $REMOTE_DIR && bash object-storage-server/init-buckets.sh >/dev/null 2>&1 && echo '  init-buckets: ok'"
ssh_ "(crontab -l 2>/dev/null | grep -v MyMiniCloud;
       echo '15 19 * * * cd \$HOME/$REMOTE_DIR && docker compose --profile ops run --rm db-backup >> logs/backup.log 2>&1 # MyMiniCloud sao lưu 02:15 giờ VN';
       echo '30 20 * * 1 cd \$HOME/$REMOTE_DIR && $DC --profile tls run --rm certbot renew -q && docker exec api-gateway-proxy-server nginx -s reload # MyMiniCloud gia hạn chứng chỉ'
      ) | crontab - && crontab -l | grep MyMiniCloud"

echo "== 6. Smoke test trên EC2 (gateway https://$DOMAIN)"
ssh_ "cd $REMOTE_DIR && SMOKE_BASE=https://$DOMAIN bash scripts/smoke-test.sh ec2 >/dev/null 2>&1; tail -1 logs/smoke-ec2.txt" || true
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
grep -E '^\[(PASS|FAIL|SKIP)\]|Tổng kết' logs/smoke-ec2.txt
echo "Portal: https://$DOMAIN/portal/"
