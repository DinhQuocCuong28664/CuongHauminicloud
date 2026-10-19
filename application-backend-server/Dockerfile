FROM python:3.12-alpine

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
