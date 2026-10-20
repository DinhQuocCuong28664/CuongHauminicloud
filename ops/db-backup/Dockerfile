FROM python:3.12-alpine

LABEL org.opencontainers.image.title="myminicloud-db-backup" \
      org.opencontainers.image.description="MyMiniCloud: MariaDB backup to MinIO (db-backups bucket) and test restore" \
      org.opencontainers.image.authors="Đinh Quốc Cường (523H0008), Nguyễn Cao Hậu (523H0025)"

# mariadb-dump and the mariadb client for backup and restore; boto3 to talk to MinIO through the S3 API
RUN apk add --no-cache mariadb-client \
 && pip install --no-cache-dir boto3==1.43.108 \
 && adduser -D -H backup

WORKDIR /app
COPY backup.py restore.py ./
USER backup

ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "/app/backup.py"]
