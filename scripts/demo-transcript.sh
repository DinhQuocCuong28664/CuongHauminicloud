#!/usr/bin/env bash
# demo-transcript.sh — rerun the demo commands from the "demo & test requirements" table of the assignment and record
# "$ command" + the real output into evidence/demo-*.txt (used to render terminal images for Chapter 4).
# Passwords appear only as variable names ($DB_ROOT_PASSWORD); their values are never printed.
#   bash scripts/demo-transcript.sh
set -u
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
mkdir -p evidence
H=localhost

# run "<shown command>"  — print the command, then run that exact string (variables expand when run, not when printed)
run() { printf '$ %s\n' "$1"; eval "$1" 2>&1 | tr -d '\r'; echo; }
out() { exec > "evidence/$1.txt"; }

if docker info --format '{{.OperatingSystem}}' 2>/dev/null | grep -q 'Docker Desktop'; then
  DIG='docker run --rm --add-host host.docker.internal:host-gateway nicolaka/netshoot:v0.16 dig @host.docker.internal'
else
  DIG='docker run --rm --network host nicolaka/netshoot:v0.16 dig @127.0.0.1'
fi

(
out demo-00-compose-ps
run "docker compose ps --format 'table {{.Name}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'"

out demo-00-network
run "docker network inspect cloud-net --format '{{range .IPAM.Config}}subnet {{.Subnet}}  gateway {{.Gateway}}{{end}}'"
run "docker network inspect cloud-net --format '{{range .Containers}}{{.Name}}  {{.IPv4Address}}{{println}}{{end}}' | sort -t. -k4 -n"

out demo-00-stats
run "docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' \$(docker compose ps -q)"

out demo-b01-web
run "curl -sI http://$H:$WEB1_PORT/"
run "curl -sI http://$H:$WEB1_PORT/blog/"

out demo-b02-app
run "curl -s http://$H:$APP_PORT/hello"
run "curl -s http://$H/api/hello"
run "curl -s http://$H:$APP_PORT/notes"

out demo-b03-db
run 'docker exec relational-database-server mariadb -uroot -p"$DB_ROOT_PASSWORD" -e "SHOW DATABASES;"'
run 'docker run --rm --network cloud-net mariadb:11.4.13 mariadb -h db -uroot -p"$DB_ROOT_PASSWORD" -e "USE minicloud; SHOW TABLES; SELECT * FROM notes;"'

out demo-b04-auth
run "curl -sI http://$H:$AUTH_PORT/auth/"
run "curl -s http://$H:$AUTH_PORT/auth/realms/master/.well-known/openid-configuration | python -m json.tool | head -8"

out demo-b06-dns
run "$DIG -p $DNS_PORT web-frontend-server.cloud.local +short"
run "$DIG -p $DNS_PORT web-frontend-server.cloud.local +noall +answer"

out demo-b07-prometheus
run "curl -s http://$H:$PROM_PORT/api/v1/targets | python -c \"import sys,json; [print(t['labels']['job'], t['scrapeUrl'], t['health']) for t in json.load(sys.stdin)['data']['activeTargets']]\""
run "curl -s 'http://$H:$PROM_PORT/api/v1/query?query=node_cpu_seconds_total' | python -c \"import sys,json; r=json.load(sys.stdin)['data']['result']; print(len(r), 'series'); [print(x['metric']['cpu'], x['metric']['mode'], x['value'][1]) for x in r[:6]]\""

out demo-b09-proxy
run "curl -sI http://$H/"
run "curl -s http://$H/api/hello"
run "curl -sI http://$H/auth/"
)
echo "Đã ghi evidence/demo-*.txt"
ls evidence/demo-*.txt
