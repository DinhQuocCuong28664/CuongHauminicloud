-- Mở rộng 3: cơ sở dữ liệu studentdb với bảng students
CREATE DATABASE IF NOT EXISTS studentdb CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE studentdb;

CREATE TABLE IF NOT EXISTS students (
  id INT PRIMARY KEY AUTO_INCREMENT,
  student_id VARCHAR(10),
  fullname VARCHAR(100),
  dob DATE,
  major VARCHAR(50)
);

INSERT INTO students (student_id, fullname, dob, major) VALUES
  ('SV001', 'Nguyễn Văn An',  '2005-03-15', 'Computer Science'),
  ('SV002', 'Trần Thị Bình',  '2005-11-02', 'Information Systems'),
  ('SV003', 'Lê Văn Cảnh',    '2005-07-20', 'Cybersecurity'),
  ('SV004', 'Phạm Thị Dung',  '2005-01-09', 'Software Engineering');
