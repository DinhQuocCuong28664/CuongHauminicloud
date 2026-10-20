#!/bin/sh
# Create buckets, set policies and upload sample files with the MinIO Client (mc) in a throwaway container.
# Usage (from the project root):  bash object-storage-server/init-buckets.sh
#   demo          private      index.html            (basic part)
#   profile-pics  public-read  avatar.jpg            (extension 5: public URL; advanced A04: Portal avatars)
#   documents     private      report.pdf            (extension 5: only via a presigned URL or through the app)
#   db-backups    private      DB backups            (advanced A09: expire after 7 days)
# Advanced: two least-privilege MinIO users (like IAM users/roles): app and backup, never the root account.
# Safe to run repeatedly.
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
    # profile-pics allows anonymous reads; demo, documents, db-backups stay private (default)
    mc anonymous set download local/profile-pics
    # Backups older than 7 days are deleted (like an S3 lifecycle rule); drop old rules so reruns add no duplicates
    mc ilm rule rm --all --force local/db-backups >/dev/null 2>&1 || true
    mc ilm rule add --expire-days 7 local/db-backups
    # Least-privilege users for the application server and the backup job
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
