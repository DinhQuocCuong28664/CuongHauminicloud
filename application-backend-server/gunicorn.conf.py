# Cấu hình gunicorn: 2 worker là đủ cho EC2 t3.medium.
# prometheus_client chạy chế độ nhiều tiến trình: mỗi worker ghi metric vào PROMETHEUS_MULTIPROC_DIR,
# /metrics gộp số liệu của mọi worker (nếu không, mỗi lần scrape chỉ thấy số liệu của một worker).
import os
import shutil

from prometheus_client import multiprocess

bind = "0.0.0.0:8081"
workers = 2
# Log request do app tự ghi dạng JSON (có request_id), nên tắt access log của gunicorn
accesslog = None
errorlog = "-"
# appuser không có thư mục home: đặt socket điều khiển của gunicorn vào /tmp
control_socket = "/tmp/gunicorn.ctl"


def on_starting(server):
    path = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if path:
        shutil.rmtree(path, ignore_errors=True)
        os.makedirs(path, exist_ok=True)


def child_exit(server, worker):
    multiprocess.mark_process_dead(worker.pid)
