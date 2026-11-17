#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_demo.py - run an advanced demo (A01..A12) against the EC2 instance from this Windows machine.

  python scripts/ec2/run_demo.py A05

What runs where:
  - checks over HTTP(S) (API, Prometheus, Grafana, MinIO) go from this machine to EC2;
  - docker commands (stop web2, backup, docker exec, docker inspect, Loki query) run ON the instance through SSH;
  - the browser steps open in the EC2 Chrome window on THIS machine (tabs from scripts/ec2/open_tabs.py,
    opened automatically when they are not open yet).
Needs scripts/ec2/instance.env (written by launch.sh) and the SSH key next to it.
"""
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent.parent
PORT = os.environ.get("DEMO_CHROME_PORT_EC2", "9223")


def ec2_chrome_alive():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1.5).read()
        return True
    except Exception:
        return False


if __name__ == "__main__":
    code = (sys.argv[1] if len(sys.argv) > 1 else "").upper()
    if not (len(code) == 3 and code[0] == "A" and code[1:].isdigit() and 1 <= int(code[1:]) <= 12):
        print("Usage: python scripts/ec2/run_demo.py A01..A12")
        sys.exit(2)
    env = dict(os.environ, DEMO_TARGET="ec2", PYTHONUTF8="1")
    if not ec2_chrome_alive():
        print(">>> Chrome EC2 chưa mở, đang mở 7 tab trên EC2 trước...")
        subprocess.run([sys.executable, str(ROOT / "scripts" / "ec2" / "open_tabs.py")], env=env, cwd=ROOT)
    sys.exit(subprocess.run([sys.executable, str(ROOT / "scripts" / "demo_advanced.py"), code], env=env, cwd=ROOT).returncode)
