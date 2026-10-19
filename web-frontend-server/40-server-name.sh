#!/bin/sh
# Chạy trong /docker-entrypoint.d trước khi nginx khởi động:
# thay chỗ __SERVER_NAME__ trong các trang HTML bằng tên bản sao (web1/web2).
set -e
find /usr/share/nginx/html -name '*.html' -exec sed -i "s/__SERVER_NAME__/${SERVER_NAME}/g" {} +
echo "40-server-name.sh: pages tagged with SERVER_NAME=${SERVER_NAME}"
