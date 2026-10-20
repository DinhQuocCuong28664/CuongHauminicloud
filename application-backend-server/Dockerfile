FROM python:3.12-alpine

LABEL org.opencontainers.image.title="myminicloud-app" \
      org.opencontainers.image.description="MyMiniCloud application server: Flask API (hello, student, students-db, secure OIDC, CRUD + RBAC, avatar MinIO, metrics, alerts)" \
      org.opencontainers.image.authors="Đinh Quốc Cường (523H0008), Nguyễn Cao Hậu (523H0025)"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py gunicorn.conf.py students.json ./

# Do not run the application as root
RUN adduser -D -H appuser
USER appuser

# Metric directory shared by the gunicorn workers (see gunicorn.conf.py)
ENV PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus \
    PYTHONUNBUFFERED=1

EXPOSE 8081
# gunicorn instead of the Flask development server
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]
