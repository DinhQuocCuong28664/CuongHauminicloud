#!/bin/bash
# Tạo user riêng cho ứng dụng thay vì dùng root. Mật khẩu lấy từ biến môi trường, không ghi cứng.
# Gọi mariadb qua socket của server tạm thời trong lần khởi tạo (không dùng hàm docker_process_sql
# vì khi file mount có quyền thực thi, như trên Windows, entrypoint chạy script chứ không "source" nó).
set -e

mariadb --protocol=socket -uroot -p"${MARIADB_ROOT_PASSWORD}" <<EOSQL
CREATE USER IF NOT EXISTS '${DB_APP_USER}'@'%' IDENTIFIED BY '${DB_APP_PASSWORD}';
GRANT SELECT ON minicloud.* TO '${DB_APP_USER}'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON studentdb.* TO '${DB_APP_USER}'@'%';
FLUSH PRIVILEGES;
EOSQL

echo "010_app_user.sh: created application user ${DB_APP_USER}"
