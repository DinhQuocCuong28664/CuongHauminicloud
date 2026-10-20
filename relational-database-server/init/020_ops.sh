#!/bin/bash
# Phần nâng cao: database "ops" lưu cảnh báo nhận từ Alertmanager (A07) và user chỉ dùng để sao lưu (A09).
# Chạy tự động ở lần khởi tạo volume đầu tiên; với volume đã có dữ liệu thì chạy bằng scripts/db-migrate.sh.
# Mọi câu lệnh đều "IF NOT EXISTS" nên chạy lại nhiều lần không sao.
set -e

mariadb --protocol=socket -uroot -p"${MARIADB_ROOT_PASSWORD}" <<EOSQL
CREATE DATABASE IF NOT EXISTS ops CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ops.alerts (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  fingerprint  VARCHAR(32)  NOT NULL,
  alertname    VARCHAR(100) NOT NULL,
  severity     VARCHAR(20),
  target       VARCHAR(150),
  status       VARCHAR(10)  NOT NULL,
  summary      VARCHAR(255),
  starts_at    DATETIME     NOT NULL,
  ends_at      DATETIME     NULL,
  received_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_alert (fingerprint, starts_at)
);

-- App ghi cảnh báo nhưng không được xoá
GRANT SELECT, INSERT, UPDATE ON ops.* TO '${DB_APP_USER}'@'%';

-- User sao lưu: chỉ đọc dữ liệu cần dump; được ghi vào database khôi phục thử studentdb_restore
CREATE USER IF NOT EXISTS '${DB_BACKUP_USER}'@'%' IDENTIFIED BY '${DB_BACKUP_PASSWORD}';
GRANT SELECT, SHOW VIEW, LOCK TABLES, TRIGGER, EVENT ON studentdb.* TO '${DB_BACKUP_USER}'@'%';
GRANT SELECT, SHOW VIEW, LOCK TABLES, TRIGGER, EVENT ON minicloud.* TO '${DB_BACKUP_USER}'@'%';
GRANT ALL PRIVILEGES ON studentdb_restore.* TO '${DB_BACKUP_USER}'@'%';
FLUSH PRIVILEGES;
EOSQL

echo "020_ops.sh: database ops, bảng alerts, user ${DB_BACKUP_USER}"
