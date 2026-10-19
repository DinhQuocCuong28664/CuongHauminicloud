#!/usr/bin/env bash
# post-start.sh — chạy sau khi Keycloak healthy, khi truy cập qua public IP (EC2) bằng HTTP.
# Realm master mặc định sslRequired=external: request từ IP công khai bị chặn với thông báo
# "HTTPS required". Bản demo không có HTTPS nên tắt yêu cầu này cho realm master
# (realm của nhóm đã đặt sslRequired=none trong file import). Hệ thống thật phải bật HTTPS.
#   bash authentication-identity-server/post-start.sh
set -eu
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

kcadm() { docker exec authentication-identity-server /opt/keycloak/bin/kcadm.sh "$@" --config /tmp/kcadm.config; }

kcadm config credentials --server http://localhost:8080/auth --realm master --user "$KC_ADMIN" --password "$KC_ADMIN_PASSWORD"
kcadm update realms/master -s sslRequired=NONE
echo "realm master: sslRequired = $(kcadm get realms/master --fields sslRequired | tr -d ' \r\n{}"' | cut -d: -f2)"
