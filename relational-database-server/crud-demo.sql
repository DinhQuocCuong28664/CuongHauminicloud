-- Minh hoạ CRUD trên studentdb.students (mở rộng 3)
-- Chạy: docker exec -i relational-database-server sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" --default-character-set=utf8mb4 -t' < relational-database-server/crud-demo.sql
USE studentdb;

SELECT '1. READ - dữ liệu ban đầu' AS buoc;
SELECT * FROM students;

SELECT '2. CREATE - thêm sinh viên SV005' AS buoc;
INSERT INTO students (student_id, fullname, dob, major)
VALUES ('SV005', 'Hoàng Văn Em', '2005-09-30', 'Data Science');
SELECT * FROM students WHERE student_id = 'SV005';

SELECT '3. UPDATE - đổi chuyên ngành của SV002' AS buoc;
UPDATE students SET major = 'Data Science' WHERE student_id = 'SV002';
SELECT * FROM students WHERE student_id = 'SV002';

SELECT '4. DELETE - xoá SV005 vừa thêm' AS buoc;
DELETE FROM students WHERE student_id = 'SV005';
SELECT COUNT(*) AS so_ban_ghi_con_lai FROM students;

SELECT '5. READ - kết quả cuối' AS buoc;
SELECT * FROM students;
