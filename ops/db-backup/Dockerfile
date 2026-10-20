FROM python:3.12-alpine

LABEL org.opencontainers.image.title="myminicloud-db-backup" \
      org.opencontainers.image.description="MyMiniCloud: sao lưu MariaDB sang MinIO (bucket db-backups) và khôi phục thử" \
      org.opencontainers.image.authors="Đinh Quốc Cường (523H0008), Nguyễn Cao Hậu (523H0025)"

# mariadb-dump và mariadb (client) để sao lưu và khôi phục; boto3 để làm việc với MinIO qua API S3
RUN apk add --no-cache mariadb-client \
 && pip install --no-cache-dir boto3==1.43.108 \
 && adduser -D -H backup

WORKDIR /app
COPY backup.py restore.py ./
USER backup

ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "/app/backup.py"]
