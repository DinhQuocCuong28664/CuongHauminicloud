#!/bin/sh
# Tạo bucket, đặt policy và upload file mẫu bằng MinIO Client (mc) chạy trong một container dùng một lần.
# Cách chạy (từ thư mục gốc dự án):  bash object-storage-server/init-buckets.sh
#   demo          private      index.html            (phần cơ bản)
#   profile-pics  public-read  avatar.jpg            (mở rộng 5: URL public; nâng cao A04: ảnh đại diện từ Portal)
#   documents     private      report.pdf            (mở rộng 5: chỉ truy cập qua URL có chữ ký hoặc qua app)
#   db-backups    private      bản sao lưu DB         (nâng cao A09: tự xoá sau 7 ngày)
# Nâng cao: hai user MinIO quyền tối thiểu (giống IAM user/role): app và backup, không dùng tài khoản root.
# Chạy lại nhiều lần không sao.
set -eu
export MSYS_NO_PATHCONV=1

cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

MC_IMAGE=pgsty/mc:RELEASE.2026-10-18T00-00-00Z

docker run --rm --network cloud-net \
  -e MC_HOST_local="http://${MINIO_ROOT_USER}:${MINIO_ROOT_PASSWORD}@object-storage-server:9000" \
  -e MINIO_APP_USER -e MINIO_APP_PASSWORD -e MINIO_BACKUP_USER -e MINIO_BACKUP_PASSWORD \
  -v "$(pwd)/web-frontend-server/html:/upload/web:ro" \
  -v "$(pwd)/object-storage-server/samples:/upload/samples:ro" \
  -v "$(pwd)/object-storage-server/policies:/policies:ro" \
  --entrypoint sh "$MC_IMAGE" -c '
    set -e
    mc mb --ignore-existing local/demo local/profile-pics local/documents local/db-backups
    mc cp /upload/web/index.html local/demo/index.html
    mc cp /upload/samples/avatar.jpg local/profile-pics/avatar.jpg
    if [ -f /upload/samples/report.pdf ]; then
      mc cp /upload/samples/report.pdf local/documents/report.pdf
    fi
    # profile-pics cho phép đọc ẩn danh; demo, documents, db-backups giữ private (mặc định)
    mc anonymous set download local/profile-pics
    # Bản sao lưu cũ hơn 7 ngày tự bị xoá (tương đương S3 lifecycle rule); xoá rule cũ để chạy lại không bị trùng
    mc ilm rule rm --all --force local/db-backups >/dev/null 2>&1 || true
    mc ilm rule add --expire-days 7 local/db-backups
    # User quyền tối thiểu cho application server và job sao lưu
    mc admin policy create local minicloud-app /policies/minicloud-app.json
    mc admin policy create local minicloud-backup /policies/minicloud-backup.json
    mc admin user add local "$MINIO_APP_USER" "$MINIO_APP_PASSWORD"
    mc admin user add local "$MINIO_BACKUP_USER" "$MINIO_BACKUP_PASSWORD"
    mc admin policy attach local minicloud-app --user "$MINIO_APP_USER" 2>/dev/null || true
    mc admin policy attach local minicloud-backup --user "$MINIO_BACKUP_USER" 2>/dev/null || true
    echo
    for b in demo profile-pics documents db-backups; do mc anonymous get local/$b; done
    mc ilm rule ls local/db-backups
    mc admin user info local "$MINIO_APP_USER"
    mc admin user info local "$MINIO_BACKUP_USER"
    echo
    mc ls --recursive local
  '
