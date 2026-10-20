#!/bin/bash
# Create a dedicated application user instead of using root. Passwords come from the environment, never hard-coded.
# Call mariadb through the socket of the temporary init server (not the docker_process_sql function,
# because when the mounted file is executable, as on Windows, the entrypoint runs it instead of sourcing it).
set -e

mariadb --protocol=socket -uroot -p"${MARIADB_ROOT_PASSWORD}" <<EOSQL
CREATE USER IF NOT EXISTS '${DB_APP_USER}'@'%' IDENTIFIED BY '${DB_APP_PASSWORD}';
GRANT SELECT ON minicloud.* TO '${DB_APP_USER}'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON studentdb.* TO '${DB_APP_USER}'@'%';
FLUSH PRIVILEGES;
EOSQL

echo "010_app_user.sh: created application user ${DB_APP_USER}"
