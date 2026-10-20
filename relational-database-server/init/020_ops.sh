#!/bin/bash
# Advanced part: the "ops" database stores alerts received from Alertmanager (A07), plus a backup-only user (A09).
# Runs automatically on the first volume initialization; on a volume that already has data use scripts/db-migrate.sh.
# Every statement uses "IF NOT EXISTS", so it is safe to run repeatedly.
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

-- The app writes alerts but may not delete them
GRANT SELECT, INSERT, UPDATE ON ops.* TO '${DB_APP_USER}'@'%';

-- Backup user: read-only on the dumped data; may write to the studentdb_restore test-restore database
CREATE USER IF NOT EXISTS '${DB_BACKUP_USER}'@'%' IDENTIFIED BY '${DB_BACKUP_PASSWORD}';
GRANT SELECT, SHOW VIEW, LOCK TABLES, TRIGGER, EVENT ON studentdb.* TO '${DB_BACKUP_USER}'@'%';
GRANT SELECT, SHOW VIEW, LOCK TABLES, TRIGGER, EVENT ON minicloud.* TO '${DB_BACKUP_USER}'@'%';
GRANT ALL PRIVILEGES ON studentdb_restore.* TO '${DB_BACKUP_USER}'@'%';
FLUSH PRIVILEGES;
EOSQL

echo "020_ops.sh: database ops, bảng alerts, user ${DB_BACKUP_USER}"
