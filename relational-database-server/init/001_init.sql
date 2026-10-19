-- Chạy một lần khi volume dữ liệu còn trống (docker-entrypoint-initdb.d)
CREATE DATABASE IF NOT EXISTS minicloud CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE minicloud;

CREATE TABLE IF NOT EXISTS notes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  title VARCHAR(100) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO notes (title) VALUES ('Hello from MariaDB!');
