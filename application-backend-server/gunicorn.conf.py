# gunicorn config: 2 workers are enough for an EC2 t3.medium.
# prometheus_client runs in multiprocess mode: each worker writes metrics to PROMETHEUS_MULTIPROC_DIR,
# and /metrics merges all workers (otherwise each scrape would only see the numbers of one worker).
import os
import shutil

from prometheus_client import multiprocess

bind = "0.0.0.0:8081"
workers = 2
# The app writes its own JSON request log (with request_id), so the gunicorn access log is off
accesslog = None
errorlog = "-"
# appuser has no home directory: put the gunicorn control socket in /tmp
control_socket = "/tmp/gunicorn.ctl"


def on_starting(server):
    path = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if path:
        shutil.rmtree(path, ignore_errors=True)
        os.makedirs(path, exist_ok=True)


def child_exit(server, worker):
    multiprocess.mark_process_dead(worker.pid)
