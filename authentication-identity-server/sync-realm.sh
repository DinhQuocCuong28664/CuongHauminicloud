#!/usr/bin/env bash
# sync-realm.sh — reload the team realm from its JSON file into the running Keycloak.
# "--import-realm" only imports a realm that does NOT exist yet, so after editing realm-523H0008-523H0025.json
# (new roles, clients...) the realm must be deleted and Keycloak restarted to import it again.
# sv01 and sv02 are recreated with SV_PASSWORD from .env; existing sessions are revoked.
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
