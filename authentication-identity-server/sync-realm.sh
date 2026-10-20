#!/usr/bin/env bash
# sync-realm.sh — nạp lại realm của nhóm từ file JSON vào Keycloak đang chạy.
# "--import-realm" chỉ nhập khi realm CHƯA tồn tại, nên sau khi sửa realm-523H0008-523H0025.json
# (thêm role, client...) phải xoá realm rồi khởi động lại Keycloak để nhập lại từ file.
# sv01, sv02 được tạo lại với mật khẩu SV_PASSWORD trong .env; phiên đăng nhập cũ bị huỷ.
#   bash authentication-identity-server/sync-realm.sh
set -eu
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

C=authentication-identity-server
kcadm() { docker exec "$C" /opt/keycloak/bin/kcadm.sh "$@" --config /tmp/kcadm.config; }
login() {
  kcadm config credentials --server http://localhost:8080/auth --realm master \
    --user "$KC_ADMIN" --password "$KC_ADMIN_PASSWORD" >/dev/null
}
wait_healthy() {
  printf 'chờ Keycloak healthy'
  until [ "$(docker inspect -f '{{.State.Health.Status}}' "$C")" = healthy ]; do printf .; sleep 3; done
  echo
}

wait_healthy
login
if kcadm get "realms/$KC_REALM" --fields realm >/dev/null 2>&1; then
  kcadm delete "realms/$KC_REALM"
  echo "đã xoá realm $KC_REALM"
fi
docker restart "$C" >/dev/null
sleep 5
wait_healthy

login
echo "client: $(kcadm get clients -r "$KC_REALM" --fields clientId --format csv --noquotes | tr -d '\r' | grep -E '^(flask-app|portal)$' | paste -sd' ')"
echo "role sv01: $(kcadm get-roles -r "$KC_REALM" --uusername sv01 --fields name --format csv --noquotes | tr -d '\r' | grep -E '^(editor|viewer)$' | paste -sd' ')"
echo "role sv02: $(kcadm get-roles -r "$KC_REALM" --uusername sv02 --fields name --format csv --noquotes | tr -d '\r' | grep -E '^(editor|viewer)$' | paste -sd' ')"
