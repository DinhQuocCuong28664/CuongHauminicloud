#!/usr/bin/env bash
# get-token.sh — extension 4: get an access token for a realm user from the Keycloak token endpoint
# (through the reverse proxy), decode the payload, then call /api/secure with a valid, a missing and a tampered token.
#   bash scripts/get-token.sh [username]        (default sv01)
# Results go to evidence/e04-token-<username>.txt
set -u
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
if python3 -c 'pass' >/dev/null 2>&1; then PY=python3; else PY=python; fi

USERNAME=${1:-sv01}
H=${SMOKE_HOST:-localhost}
BASE="http://$H:$PROXY_PORT"
TOKEN_URL="$BASE/auth/realms/$KC_REALM/protocol/openid-connect/token"
mkdir -p evidence

{
echo "Realm:          $KC_REALM"
echo "Client:         $OIDC_CLIENT_ID (public, Direct Access Grants)"
echo "Token endpoint: $TOKEN_URL"
echo

echo "\$ curl -X POST <token endpoint> -d grant_type=password -d client_id=$OIDC_CLIENT_ID -d username=$USERNAME -d password=***"
RESP=$(curl -s -X POST "$TOKEN_URL" -d grant_type=password -d "client_id=$OIDC_CLIENT_ID" \
         -d "username=$USERNAME" --data-urlencode "password=$SV_PASSWORD")
TOKEN=$(printf '%s' "$RESP" | $PY -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
printf '%s' "$RESP" | $PY -c "
import sys, json
d = json.load(sys.stdin)
print('token_type:', d.get('token_type'), '| expires_in:', d.get('expires_in'), 's | access_token:', d.get('access_token', '')[:40] + '...')"
echo
echo "Payload của access token (đã giải mã base64url):"
printf '%s' "$TOKEN" | $PY -c "
import sys, json, base64
p = sys.stdin.read().split('.')[1]
claims = json.loads(base64.urlsafe_b64decode(p + '=' * (-len(p) % 4)))
for k in ('iss', 'aud', 'azp', 'preferred_username', 'name', 'email', 'iat', 'exp'):
    print(f'  {k}: {claims.get(k)}')"
echo

echo "\$ curl $BASE/api/secure -H 'Authorization: Bearer <token>'"
curl -s -w '  [HTTP %{http_code}]\n' "$BASE/api/secure" -H "Authorization: Bearer $TOKEN"
echo
echo "\$ curl $BASE/api/secure            (không gửi token)"
curl -s -w '  [HTTP %{http_code}]\n' "$BASE/api/secure"
echo
echo "\$ curl $BASE/api/secure -H 'Authorization: Bearer <token bị sửa chữ ký>'"
BAD="${TOKEN%?????}AAAAA"
curl -s -w '  [HTTP %{http_code}]\n' "$BASE/api/secure" -H "Authorization: Bearer $BAD"
} | tr -d '\r' | tee "evidence/e04-token-${USERNAME}.txt"   # Python on Windows writes \r\n to pipes
