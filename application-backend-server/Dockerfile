FROM python:3.12-alpine

LABEL org.opencontainers.image.title="myminicloud-app" \
      org.opencontainers.image.description="MyMiniCloud application server: Flask API (hello, notes, student, students-db, secure OIDC)" \
      org.opencontainers.image.authors="Đinh Quốc Cường (523H0008), Nguyễn Cao Hậu (523H0025)"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py students.json ./

# Không chạy ứng dụng bằng root
RUN adduser -D -H appuser
USER appuser

EXPOSE 8081
# gunicorn thay cho server phát triển của Flask; 2 worker là đủ cho EC2 t3.medium
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8081", "--access-logfile", "-", "app:app"]
