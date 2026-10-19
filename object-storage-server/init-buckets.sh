#!/bin/sh
# Tạo bucket, đặt policy và upload file mẫu bằng MinIO Client (mc) chạy trong một container dùng một lần.
# Cách chạy (từ thư mục gốc dự án):  bash object-storage-server/init-buckets.sh
#   demo          private      index.html            (phần cơ bản)
#   profile-pics  public-read  avatar.jpg            (mở rộng 5: URL public)
#   documents     private      report.pdf            (mở rộng 5: chỉ truy cập qua URL có chữ ký)
set -eu
export MSYS_NO_PATHCONV=1

cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

MC_IMAGE=pgsty/mc:RELEASE.2026-10-18T00-00-00Z

docker run --rm --network cloud-net \
  -e MC_HOST_local="http://${MINIO_ROOT_USER}:${MINIO_ROOT_PASSWORD}@object-storage-server:9000" \
  -v "$(pwd)/web-frontend-server/html:/upload/web:ro" \
  -v "$(pwd)/object-storage-server/samples:/upload/samples:ro" \
  --entrypoint sh "$MC_IMAGE" -c '
    set -e
    mc mb --ignore-existing local/demo local/profile-pics local/documents
    mc cp /upload/web/index.html local/demo/index.html
    mc cp /upload/samples/avatar.jpg local/profile-pics/avatar.jpg
    if [ -f /upload/samples/report.pdf ]; then
      mc cp /upload/samples/report.pdf local/documents/report.pdf
    fi
    # profile-pics cho phép đọc ẩn danh; demo và documents giữ private (mặc định)
    mc anonymous set download local/profile-pics
    echo
    for b in demo profile-pics documents; do mc anonymous get local/$b; done
    echo
    mc ls --recursive local
  '
