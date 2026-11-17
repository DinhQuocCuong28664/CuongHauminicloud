#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""open_tabs.py - open the same 7 demo tabs as DEMO.bat key 8, but for the EC2 instance (HTTPS), and log in.

Run it on this machine (Chrome with the tabs opens here; nothing is copied to the server).
  python scripts/ec2/open_tabs.py            open the tabs (or just bring Chrome to the front when already open)
  python scripts/ec2/open_tabs.py reopen     close and log in again
  python scripts/ec2/open_tabs.py close      close the EC2 Chrome

Tabs: 1 Home, 2 Portal (sv01), 3 Blog, 4 Keycloak admin, 5 MinIO, 6 Grafana, 7 Prometheus.
Address comes from scripts/ec2/instance.env (PUBLIC_IP; it changes on every Stop/Start, run launch.sh first).
Grafana, Prometheus and MinIO are reachable only from the IP that ran launch.sh (security group).
The EC2 Chrome uses its own debugging port (9223) and profile, so it can stay open next to the local one.
"""
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent.parent
AUTO_LOGIN = ROOT / "scripts" / "auto_login.py"
PORT = os.environ.get("DEMO_CHROME_PORT_EC2", "9223")


def alive():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1.5).read()
        return True
    except Exception:
        return False


def run(mode):
    env = dict(os.environ, DEMO_TARGET="ec2", PYTHONUTF8="1")
    return subprocess.run([sys.executable, str(AUTO_LOGIN), mode], env=env, cwd=ROOT).returncode


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "auto"
    inst = (ROOT / "scripts" / "ec2" / "instance.env").read_text(encoding="utf-8")
    ip = next((l.split("=", 1)[1].strip() for l in inst.splitlines() if l.startswith("PUBLIC_IP=")), "")
    print(f"EC2: https://{ip.replace('.', '-')}.sslip.io/portal/")
    if arg == "close":
        sys.exit(run("close"))
    if arg == "reopen":
        run("close")
        sys.exit(run("open"))
    sys.exit(run("focus") if alive() else run("open"))
