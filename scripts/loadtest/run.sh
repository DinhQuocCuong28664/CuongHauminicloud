#!/usr/bin/env bash
# run.sh — chạy các kịch bản k6 trong scripts/loadtest/scenarios.js bằng container grafana/k6 gắn vào cloud-net.
#   bash scripts/loadtest/run.sh [nhãn]          ví dụ: bash scripts/loadtest/run.sh local   (hoặc ec2)
# Kết quả: evidence/k6-<nhãn>-<kịch bản>.json (summary đầy đủ của k6) và evidence/k6-<nhãn>.txt (bảng tóm tắt).
# k6 chạy cùng máy với hệ thống nên số liệu là số so sánh giữa các kịch bản, không phải năng lực tối đa.
set -u
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/../.."
LABEL=${1:-local}
K6=grafana/k6:2.3.0
OUTDIR=scripts/loadtest/out
mkdir -p "$OUTDIR" evidence
if python3 -c 'pass' >/dev/null 2>&1; then PY=python3; else PY=python; fi

k6() {   # k6 <kịch bản>   (IP tĩnh 10.10.10.91 để không chiếm IP của container đang tạm dừng)
  docker run --rm --network cloud-net --ip 10.10.10.91 -v "$(pwd)/scripts/loadtest:/scripts" \
    -e SCENARIO="$1" -e OUT="/scripts/out/$1.json" "$K6" run --quiet /scripts/scenarios.js >/dev/null 2>&1
  cp "$OUTDIR/$1.json" "evidence/k6-$LABEL-$1.json"
}
wait_healthy() {
  until [ "$(docker inspect -f '{{.State.Health.Status}}' "$1")" = healthy ]; do sleep 2; done
}

docker image inspect "$K6" >/dev/null 2>&1 || docker pull -q "$K6" >/dev/null

echo "== web: 2 web server"; k6 web; cp "$OUTDIR/web.json" "$OUTDIR/web-2.json"
docker stop web-frontend-server2 >/dev/null; sleep 6
echo "== web: chỉ còn web1"; k6 web; cp "$OUTDIR/web.json" "$OUTDIR/web-1.json"; cp "$OUTDIR/web.json" "evidence/k6-$LABEL-web-1.json"
docker start web-frontend-server2 >/dev/null; wait_healthy web-frontend-server2; sleep 6
cp "$OUTDIR/web-2.json" "evidence/k6-$LABEL-web.json"

echo "== failover: dừng web2 ở giây 20, bật lại ở giây 40"
( sleep 20; docker stop web-frontend-server2 >/dev/null; sleep 20; docker start web-frontend-server2 >/dev/null ) &
k6 failover
wait; wait_healthy web-frontend-server2

echo "== ratelimit"; sleep 3; k6 ratelimit
echo "== api"; k6 api

# Bảng tóm tắt
$PY - "$LABEL" <<'EOF' | tee "evidence/k6-$LABEL.txt"
import json, sys
sys.stdout.reconfigure(encoding="utf-8")
label = sys.argv[1]
def load(name):
    return json.load(open(f"evidence/k6-{label}-{name}.json", encoding="utf-8"))["metrics"]
def row(title, m, extra=""):
    d = m["http_req_duration"]["values"]
    reqs = m["http_reqs"]["values"]
    failed = m["http_req_failed"]["values"]["rate"] * 100
    print(f"{title:<34} {reqs['count']:>7} req {reqs['rate']:>8.1f} req/s  p50 {d['med']:>6.1f} ms  "
          f"p95 {d['p(95)']:>6.1f} ms  max {d['max']:>7.1f} ms  lỗi {failed:5.2f}%{extra}")
def checks(m, *names):
    out = []
    for n in names:
        k = f"checks{{check:{n}}}"
        v = m.get(k, {}).get("values")
        out.append(f"{n}: {v['passes']}" if v else "")
    return ", ".join(x for x in out if x)
def check_counts(name):
    data = json.load(open(f"evidence/k6-{label}-{name}.json", encoding="utf-8"))
    res = {}
    def walk(g):
        for c in g.get("checks", []):
            res[c["name"]] = (c["passes"], c["fails"])
        for sub in g.get("groups", []):
            walk(sub)
    walk(data["root_group"])
    return res
print(f"Kiểm thử tải k6 — nhãn {label}")
for name, title in (("web", "web: 2 web server, 20 VU"), ("web-1", "web: chỉ web1, 20 VU"),
                    ("failover", "failover: dừng/bật web2, 20 VU")):
    c = check_counts(name)
    row(title, load(name), f"  web1/web2 = {c['served by web1'][0]}/{c['served by web2'][0]}")
c = check_counts("ratelimit")
row("ratelimit: 30 req/s vào /api/hello", load("ratelimit"),
    f"  200 = {c['status 200'][0]}, 429 = {c['status 429'][0]}")
m = load("api")
row("api: /hello + /students-db, 20 VU", m)
for ep in ("GET /hello", "GET /students-db"):
    k = f"http_req_duration{{name:{ep}}}"
    if k in m:
        d = m[k]["values"]
        print(f"   {ep:<20} p50 {d['med']:6.1f} ms  p95 {d['p(95)']:6.1f} ms  max {d['max']:7.1f} ms")
EOF
