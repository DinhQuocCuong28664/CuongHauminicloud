"""Generate the 4 advanced Grafana dashboards (provisioning/dashboards/*.json).

    python monitoring-grafana-dashboard-server/build_dashboards.py

Built by a script instead of hand-edited JSON so PromQL/LogQL queries stay readable and the layout consistent.
"""
import json
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "provisioning", "dashboards")
PROM = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}
PROJECT = 'container_label_com_docker_compose_project="cuonghauminicloud"'

_next_id = 0


def _id():
    global _next_id
    _next_id += 1
    return _next_id


def target(expr, legend="", ds=PROM, ref="A", instant=False, fmt=None):
    t = {"refId": ref, "datasource": ds, "expr": expr}
    if legend:
        t["legendFormat"] = legend
    if instant:
        t["instant"] = True
        t["range"] = False
    if fmt:
        t["format"] = fmt
    return t


def timeseries(title, targets, x, y, w=12, h=8, unit="short", stack=False, desc=""):
    custom = {"fillOpacity": 12, "lineWidth": 2}
    if stack:
        custom["stacking"] = {"mode": "normal", "group": "A"}
    return {
        "id": _id(), "type": "timeseries", "title": title, "description": desc,
        "gridPos": {"x": x, "y": y, "w": w, "h": h}, "datasource": targets[0]["datasource"],
        "targets": targets,
        "fieldConfig": {"defaults": {"unit": unit, "custom": custom}, "overrides": []},
        "options": {"legend": {"displayMode": "table", "placement": "right", "calcs": ["lastNotNull", "max"]},
                    "tooltip": {"mode": "multi", "sort": "desc"}},
    }


def stat(title, expr, x, y, w=4, h=4, unit="short", decimals=None, steps=None, desc=""):
    defaults = {"unit": unit, "thresholds": {"mode": "absolute", "steps": steps or [{"color": "green", "value": None}]}}
    if decimals is not None:
        defaults["decimals"] = decimals
    return {
        "id": _id(), "type": "stat", "title": title, "description": desc,
        "gridPos": {"x": x, "y": y, "w": w, "h": h}, "datasource": PROM,
        "targets": [target(expr, instant=True)],
        "fieldConfig": {"defaults": defaults, "overrides": []},
        "options": {"colorMode": "background", "graphMode": "none", "textMode": "value",
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}},
    }


def logs(title, expr, x, y, w=24, h=12, desc=""):
    return {
        "id": _id(), "type": "logs", "title": title, "description": desc,
        "gridPos": {"x": x, "y": y, "w": w, "h": h}, "datasource": LOKI,
        "targets": [target(expr, ds=LOKI)],
        "options": {"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending",
                    "enableLogDetails": True, "prettifyLogMessage": False, "dedupStrategy": "none"},
    }


def dashboard(uid, title, desc, panels, variables=(), refresh="10s", time_from="now-30m"):
    for i, p in enumerate(panels, 1):   # panel ids start at 1 in each dashboard (used by viewPanel=<id>)
        p["id"] = i
    return {
        "uid": uid, "title": title, "description": desc,
        "tags": ["myminicloud", "nang-cao", "523H0008", "523H0025"],
        "timezone": "browser", "refresh": refresh, "time": {"from": time_from, "to": "now"},
        "schemaVersion": 39, "editable": True, "templating": {"list": list(variables)},
        "panels": panels,
    }


def prom_var(name, label, query, multi=True):
    return {"name": name, "label": label, "type": "query", "datasource": PROM, "query": query,
            "definition": query, "refresh": 2, "multi": multi, "includeAll": True, "allValue": ".*",
            "current": {"selected": True, "text": ["All"], "value": ["$__all"]}, "sort": 1}


def loki_var(name, label, lbl):
    return {"name": name, "label": label, "type": "query", "datasource": LOKI,
            "query": {"type": 1, "label": lbl, "stream": "", "refId": "LokiVariableQueryEditor-VariableQuery"},
            "definition": f"label_values({lbl})", "refresh": 2, "multi": True, "includeAll": True,
            "allValue": ".+", "current": {"selected": True, "text": ["All"], "value": ["$__all"]}, "sort": 1}


def textbox(name, label, default=""):
    return {"name": name, "label": label, "type": "textbox", "query": default,
            "current": {"text": default, "value": default}}


# ---------------------------------------------------------------- 1. Container (cAdvisor)
CON = 'name=~"$container"'
containers = dashboard(
    "containers-523h0008-523h0025", "Containers – MyMiniCloud (cAdvisor)",
    "Nâng cao A06: CPU, RAM, mạng của từng container, tương đương CloudWatch Container Insights",
    [
        stat("Container đang chạy", f"count(time() - container_last_seen{{{PROJECT}}} < 60)", 0, 0, w=6),
        stat("Tổng RAM các container", f"sum(container_memory_working_set_bytes{{{PROJECT}}})", 6, 0, w=6, unit="bytes"),
        stat("Tổng CPU các container (% một lõi)",
             f"sum(rate(container_cpu_usage_seconds_total{{{PROJECT}}}[1m])) * 100", 12, 0, w=6, unit="percent", decimals=1),
        stat("Container gần chạm giới hạn RAM",
             f"count((container_memory_working_set_bytes{{{PROJECT}}} / (container_spec_memory_limit_bytes{{{PROJECT}}} > 0)) > 0.8) or vector(0)",
             18, 0, w=6, steps=[{"color": "green", "value": None}, {"color": "red", "value": 1}]),
        timeseries("CPU theo container (% một lõi)",
                   [target(f"sum by (name) (rate(container_cpu_usage_seconds_total{{{CON}}}[1m])) * 100", "{{name}}")],
                   0, 4, unit="percent"),
        timeseries("RAM đang dùng theo container (working set)",
                   [target(f"sum by (name) (container_memory_working_set_bytes{{{CON}}})", "{{name}}")],
                   12, 4, unit="bytes"),
        timeseries("Mạng nhận theo container",
                   [target(f"sum by (name) (rate(container_network_receive_bytes_total{{{CON}}}[1m]))", "{{name}}")],
                   0, 12, unit="Bps"),
        timeseries("Mạng gửi theo container",
                   [target(f"sum by (name) (rate(container_network_transmit_bytes_total{{{CON}}}[1m]))", "{{name}}")],
                   12, 12, unit="Bps"),
        timeseries("RAM so với giới hạn (mem_limit)",
                   [target(f"container_memory_working_set_bytes{{{CON}}} / (container_spec_memory_limit_bytes{{{CON}}} > 0)",
                           "{{name}}")],
                   0, 20, w=24, unit="percentunit",
                   desc="Chỉ hiện container có khai báo giới hạn RAM trong docker-compose.yml"),
    ],
    variables=[prom_var("container", "Container", f"label_values(container_last_seen{{{PROJECT}}}, name)")],
)

# ---------------------------------------------------------------- 2. API (RED)
REQ = "minicloud_http_requests_total"
DUR = "minicloud_http_request_duration_seconds_bucket"
api = dashboard(
    "api-red-523h0008-523h0025", "API – RED metrics (application-backend-server)",
    "Nâng cao A06: Rate, Errors, Duration của Flask API, đo bằng prometheus_client trong app",
    [
        stat("Request/giây", f"sum(rate({REQ}[1m]))", 0, 0, w=6, unit="reqps", decimals=2),
        stat("Tỉ lệ lỗi 5xx", f"100 * sum(rate({REQ}{{status=~\"5..\"}}[5m])) / sum(rate({REQ}[5m])) or vector(0)",
             6, 0, w=6, unit="percent", decimals=2,
             steps=[{"color": "green", "value": None}, {"color": "orange", "value": 1}, {"color": "red", "value": 5}]),
        stat("Độ trễ p95", f"histogram_quantile(0.95, sum by (le) (rate({DUR}[5m])))", 12, 0, w=6, unit="s", decimals=3,
             steps=[{"color": "green", "value": None}, {"color": "orange", "value": 0.3}, {"color": "red", "value": 0.5}]),
        stat("Từ chối do thiếu quyền (401/403, 5 phút)",
             f"sum(increase({REQ}{{status=~\"401|403\"}}[5m])) or vector(0)", 18, 0, w=6, decimals=0),
        timeseries("Rate: request/giây theo endpoint",
                   [target(f"sum by (endpoint) (rate({REQ}[1m]))", "{{endpoint}}")], 0, 4, unit="reqps", stack=True),
        timeseries("Errors: request/giây theo mã trạng thái",
                   [target(f"sum by (status) (rate({REQ}[1m]))", "{{status}}")], 12, 4, unit="reqps", stack=True),
        timeseries("Duration: p50 / p95 / p99 toàn API",
                   [target(f"histogram_quantile(0.50, sum by (le) (rate({DUR}[1m])))", "p50", ref="A"),
                    target(f"histogram_quantile(0.95, sum by (le) (rate({DUR}[1m])))", "p95", ref="B"),
                    target(f"histogram_quantile(0.99, sum by (le) (rate({DUR}[1m])))", "p99", ref="C")],
                   0, 12, unit="s"),
        timeseries("Duration: p95 theo endpoint",
                   [target(f"histogram_quantile(0.95, sum by (le, endpoint) (rate({DUR}[1m])))", "{{endpoint}}")],
                   12, 12, unit="s"),
    ],
)

# ---------------------------------------------------------------- 3. Centralized logs (Loki)
SEL = '{container=~"$container"}'
logs_db = dashboard(
    "logs-523h0008-523h0025", "Logs – MyMiniCloud (Loki)",
    "Nâng cao A05: log tập trung của mọi container; tra một request theo request_id xuyên proxy và app",
    [
        timeseries("Số dòng log/phút theo container",
                   [target(f"sum by (container) (count_over_time({SEL} [1m]))", "{{container}}", ds=LOKI)],
                   0, 0, unit="short", stack=True),
        timeseries("Mã trạng thái tại gateway (đếm từ access log)",
                   [target('sum by (status) (count_over_time({service="api-gateway-proxy-server"} | json | __error__="" [1m]))',
                           "{{status}}", ds=LOKI)],
                   12, 0, unit="short", stack=True,
                   desc="Thấy cả 429 do gateway giới hạn tốc độ, thứ mà metric của app không thấy"),
        logs("Log theo container (lọc bằng ô Tìm chuỗi)", f'{SEL} |= "$search"', 0, 8, h=12),
        logs("Truy vết một request theo request_id (proxy → app)",
             '{service=~"api-gateway-proxy-server|application-backend-server"} |= "$request_id" | json | request_id="$request_id"',
             0, 20, h=8, desc="Dán giá trị header X-Request-ID vào ô request_id"),
        logs("Log lỗi và cảnh báo", '{level=~"error|warn"}', 0, 28, h=8),
    ],
    variables=[loki_var("container", "Container", "container"),
               textbox("search", "Tìm chuỗi"),
               textbox("request_id", "request_id", "none")],
)

# ---------------------------------------------------------------- 4. Overview
overview = dashboard(
    "overview-523h0008-523h0025", "MyMiniCloud – Overview (523H0008 & 523H0025)",
    "Một màn hình tình trạng toàn hệ thống: target, cảnh báo, máy chủ, container, API, log lỗi",
    [
        stat("Target UP", "sum(up)", 0, 0, w=4),
        stat("Target DOWN", "count(up == 0) or vector(0)", 4, 0, w=4,
             steps=[{"color": "green", "value": None}, {"color": "red", "value": 1}]),
        stat("Cảnh báo firing", 'count(ALERTS{alertstate="firing"}) or vector(0)', 8, 0, w=4,
             steps=[{"color": "green", "value": None}, {"color": "red", "value": 1}]),
        stat("Container chạy", f"count(time() - container_last_seen{{{PROJECT}}} < 60)", 12, 0, w=4),
        stat("CPU host", '100 - avg(rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100', 16, 0, w=4,
             unit="percent", decimals=1,
             steps=[{"color": "green", "value": None}, {"color": "orange", "value": 70}, {"color": "red", "value": 85}]),
        stat("RAM host", "100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)", 20, 0, w=4,
             unit="percent", decimals=1,
             steps=[{"color": "green", "value": None}, {"color": "orange", "value": 75}, {"color": "red", "value": 90}]),
        {
            "id": _id(), "type": "table", "title": "Cảnh báo đang hoạt động",
            "gridPos": {"x": 0, "y": 4, "w": 12, "h": 8}, "datasource": PROM,
            "targets": [target('ALERTS{alertstate=~"firing|pending"}', instant=True, fmt="table")],
            "transformations": [{"id": "organize", "options": {
                "excludeByName": {"Time": True, "Value": True, "__name__": True},
                "indexByName": {"alertname": 0, "alertstate": 1, "severity": 2, "name": 3, "job": 4, "instance": 5}}}],
            "options": {"showHeader": True},
        },
        timeseries("Request/giây vào web (nginx) và API (Flask)",
                   [target("rate(nginx_http_requests_total[1m])", "web1 (nginx)", ref="A"),
                    target(f"sum(rate({REQ}[1m]))", "API", ref="B")],
                   12, 4, unit="reqps"),
        timeseries("Top 5 container theo RAM",
                   [target(f"topk(5, sum by (name) (container_memory_working_set_bytes{{{PROJECT}}}))", "{{name}}")],
                   0, 12, unit="bytes"),
        timeseries("Độ trễ p95 của API",
                   [target(f"histogram_quantile(0.95, sum by (le) (rate({DUR}[1m])))", "p95")], 12, 12, unit="s"),
        logs("Log lỗi gần nhất", '{level=~"error|warn"}', 0, 20, h=9),
    ],
)

for name, d in (("containers", containers), ("api-red", api), ("logs", logs_db), ("overview", overview)):
    path = os.path.join(OUT, f"{name}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("ghi", path, len(d["panels"]), "panel")
