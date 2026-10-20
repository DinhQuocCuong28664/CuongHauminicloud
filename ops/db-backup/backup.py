"""Sao lưu MariaDB sang object storage (nâng cao A09, tương đương RDS snapshot lưu trên S3).

Mỗi database dump riêng một file (khôi phục được sang database tên khác), nén gzip rồi đưa vào
bucket db-backups. Bucket có lifecycle rule tự xoá bản cũ hơn 7 ngày (init-buckets.sh).

    docker compose --profile ops run --rm db-backup
"""
import datetime
import gzip
import hashlib
import os
import subprocess
import sys
import time

import boto3
from botocore.config import Config

sys.stdout.reconfigure(encoding="utf-8")

DB_HOST = os.getenv("DB_HOST", "db.cloud.local")
DB_USER = os.getenv("DB_USER", "minicloud_backup")   # mật khẩu đọc từ biến MYSQL_PWD, không đưa lên dòng lệnh
DATABASES = os.getenv("BACKUP_DATABASES", "studentdb minicloud").split()
BUCKET = os.getenv("BACKUP_BUCKET", "db-backups")


def s3_client():
    return boto3.client(
        "s3", endpoint_url=os.getenv("S3_ENDPOINT", "http://s3.cloud.local:9000"), region_name="us-east-1",
        aws_access_key_id=os.environ["S3_ACCESS_KEY"], aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def dump(database):
    cmd = ["mariadb-dump", "-h", DB_HOST, "-u", DB_USER, "--single-transaction", "--no-tablespaces",
           "--routines", "--triggers", "--skip-comments", database]
    return subprocess.run(cmd, check=True, capture_output=True).stdout


def main():
    s3 = s3_client()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    print(f"Sao lưu {', '.join(DATABASES)} từ {DB_HOST} lúc {stamp} UTC -> s3://{BUCKET}/")
    for db in DATABASES:
        t0 = time.time()
        raw = dump(db)
        data = gzip.compress(raw, compresslevel=9)
        key = f"{db}/{db}-{stamp}.sql.gz"
        digest = hashlib.sha256(data).hexdigest()
        s3.put_object(Bucket=BUCKET, Key=key, Body=data, ContentType="application/gzip",
                      Metadata={"database": db, "sha256": digest, "source-host": DB_HOST})
        print(f"  {key:<45} dump {len(raw):>8} B  gzip {len(data):>7} B  "
              f"({100 * len(data) / max(len(raw), 1):.0f}%)  {time.time() - t0:.2f}s  sha256 {digest[:12]}…")

    print("\nCác bản sao lưu hiện có:")
    for obj in s3.list_objects_v2(Bucket=BUCKET).get("Contents", []):
        print(f"  {obj['LastModified']:%Y-%m-%d %H:%M:%S}  {obj['Size']:>7} B  {obj['Key']}")
    rules = s3.get_bucket_lifecycle_configuration(Bucket=BUCKET).get("Rules", [])
    for r in rules:
        print(f"\nLifecycle: rule {r.get('ID')} {r.get('Status')}, xoá sau {r.get('Expiration', {}).get('Days')} ngày")


if __name__ == "__main__":
    main()
