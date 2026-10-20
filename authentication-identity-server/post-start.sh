#!/usr/bin/env bash
# post-start.sh — run after Keycloak is healthy, when it is reached over HTTP through a public IP (EC2).
# The master realm defaults to sslRequired=external: requests from public IPs are rejected with
# "HTTPS required". The demo has no HTTPS, so this requirement is turned off for the master realm
# (the team realm already sets sslRequired=none in its import file). A real system must enable HTTPS.
#   bash authentication-identity-server/post-start.sh
set -eu
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

kcadm() { docker exec authentication-identity-server /opt/keycloak/bin/kcadm.sh "$@" --config /tmp/kcadm.config; }

kcadm config credentials --server http://localhost:8080/auth --realm master --user "$KC_ADMIN" --password "$KC_ADMIN_PASSWORD"
# Defaults to NONE (HTTP through a public IP). Once EC2 has HTTPS: bash post-start.sh EXTERNAL
# (HTTPS required only for public addresses, the Keycloak default)
kcadm update realms/master -s "sslRequired=${1:-NONE}"
echo "realm master: sslRequired = $(kcadm get realms/master --fields sslRequired | tr -d ' \r\n{}"' | cut -d: -f2)"
