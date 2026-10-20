#!/usr/bin/env bash
# db-migrate.sh — chạy lại các script khởi tạo có thể chạy nhiều lần (020_ops.sh...) trên volume MariaDB đã có dữ liệu.
# Script trong /docker-entrypoint-initdb.d chỉ tự chạy khi volume còn trống, nên phần nâng cao cần lệnh này
# trên máy đã chạy bản cũ (máy cá nhân, EC2).
#   bash scripts/db-migrate.sh
set -eu
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."

for f in relational-database-server/init/020_*.sh; do
  echo "== $(basename "$f")"
  docker exec relational-database-server bash "/docker-entrypoint-initdb.d/$(basename "$f")"
done
