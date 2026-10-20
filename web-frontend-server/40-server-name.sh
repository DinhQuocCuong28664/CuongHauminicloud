#!/bin/sh
# Runs from /docker-entrypoint.d before nginx starts:
# replaces __SERVER_NAME__ in the HTML pages with the replica name (web1/web2).
set -e
find /usr/share/nginx/html -name '*.html' -exec sed -i "s/__SERVER_NAME__/${SERVER_NAME}/g" {} +
echo "40-server-name.sh: pages tagged with SERVER_NAME=${SERVER_NAME}"
