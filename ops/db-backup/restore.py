"""Khôi phục thử bản sao lưu mới nhất sang một database riêng rồi so sánh với bản gốc (nâng cao A09).

Sao lưu chỉ có giá trị khi khôi phục được: script tải bản studentdb mới nhất từ bucket db-backups,
kiểm tra sha256, nạp vào database studentdb_restore và so số dòng, tổng kiểm tra của từng bảng.

    docker compose --profile ops run --rm --entrypoint python db-backup /app/restore.py
"""
import gzip
import hashlib
import os
import subprocess
import sys

from backup import BUCKET, DB_HOST, DB_USER, s3_client

sys.stdout.reconfigure(encoding="utf-8")

SOURCE = os.getenv("RESTORE_SOURCE", "studentdb")
TARGET = os.getenv("RESTORE_TARGET", "studentdb_restore")


def sql(statement, database=None):
    cmd = ["mariadb", "-h", DB_HOST, "-u", DB_USER, "-N", "-B", "-e", statement]
    if database:
        cmd.insert(1, f"--database={database}")
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()


def table_stats(database):
    stats = {}
    for table in sql("SHOW TABLES", database).splitlines():
        count = sql(f"SELECT COUNT(*) FROM `{table}`", database)
        checksum = sql(f"CHECKSUM TABLE `{table}`", database).split("\t")[-1]
        stats[table] = (int(count), checksum)
    return stats


def main():
    s3 = s3_client()
    objs = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"{SOURCE}/").get("Contents", [])
    if not objs:
        sys.exit(f"Không có bản sao lưu nào của {SOURCE} trong s3://{BUCKET}/")
    latest = max(objs, key=lambda o: o["LastModified"])
    obj = s3.get_object(Bucket=BUCKET, Key=latest["Key"])
    data = obj["Body"].read()
    expected = obj["Metadata"].get("sha256")
    actual = hashlib.sha256(data).hexdigest()
    print(f"Bản sao lưu: s3://{BUCKET}/{latest['Key']} ({len(data)} B, {latest['LastModified']:%Y-%m-%d %H:%M:%S} UTC)")
    print(f"sha256: {'khớp' if actual == expected else 'KHÔNG KHỚP'} ({actual[:12]}…)")
    if actual != expected:
        sys.exit(1)

    sql(f"DROP DATABASE IF EXISTS `{TARGET}`")
    sql(f"CREATE DATABASE `{TARGET}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    subprocess.run(["mariadb", "-h", DB_HOST, "-u", DB_USER, TARGET], input=gzip.decompress(data), check=True)
    print(f"Đã nạp vào database {TARGET}\n")

    src, dst = table_stats(SOURCE), table_stats(TARGET)
    ok = True
    print(f"{'Bảng':<12} {'gốc (dòng, checksum)':<26} {'khôi phục (dòng, checksum)':<28} kết quả")
    for table in sorted(set(src) | set(dst)):
        same = src.get(table) == dst.get(table)
        ok &= same
        print(f"{table:<12} {str(src.get(table)):<26} {str(dst.get(table)):<28} {'KHỚP' if same else 'KHÁC'}")
    print("\nKẾT LUẬN:", "khôi phục đúng" if ok else "dữ liệu khác bản gốc (có thay đổi sau lần sao lưu?)")
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
