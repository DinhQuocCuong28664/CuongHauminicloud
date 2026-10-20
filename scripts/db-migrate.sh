#!/usr/bin/env bash
# db-migrate.sh — rerun the idempotent init scripts (020_ops.sh...) on a MariaDB volume that already has data.
# Scripts in /docker-entrypoint-initdb.d only run on an empty volume, so the advanced part needs this command
# on machines that ran the old version (personal machine, EC2).
#   bash scripts/db-migrate.sh
set -eu
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."

for f in relational-database-server/init/020_*.sh; do
  echo "== $(basename "$f")"
  docker exec relational-database-server bash "/docker-entrypoint-initdb.d/$(basename "$f")"
done
