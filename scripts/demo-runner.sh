#!/usr/bin/env bash
# demo-runner.sh — Điều khiển chạy live demo tuần tự hoặc theo từng bước
# Có cơ chế Auto Re-check liên tục (polling) tự bắt khi Docker Desktop và Container bật.
set -u
export MSYS_NO_PATHCONV=1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
export COMPOSE_PROJECT_NAME=cuonghauminicloud
set -a; . ./.env; set +a

NETSHOOT=nicolaka/netshoot:v0.16

ensure_docker() {
  local warned=0
  # 1. Chờ Docker daemon liên tục
  while ! docker info >/dev/null 2>&1; do
    if [ $warned -eq 0 ]; then
      echo ""
      echo "========================================================================="
      echo " ⏳ ĐANG CHỜ DOCKER DESKTOP KHỞI ĐỘNG..."
      echo "========================================================================="
      echo " Chưa phát hiện Docker Engine đang chạy."
      echo " 👉 Vui lòng BẬT DOCKER DESKTOP trên máy tính."
      echo " 👉 Script đang TỰ ĐỘNG QUÉT LIÊN TỤC và sẽ TỰ BẮT NGAY khi Docker bật!"
      echo "========================================================================="
      warned=1
    fi
    printf "\r>>> Đang quét Docker Engine liên tục... (tự nhận diện khi bật) "
    sleep 1.5
  done

  # 2. Chờ đủ 16 container
  local up_count
  up_count=$(docker compose -p cuonghauminicloud ps -q 2>/dev/null | wc -l)
  if [ "$up_count" -lt 16 ]; then
    echo ""
    echo "========================================================================="
    echo " ⚠️  PHÁT HIỆN CÓ $up_count/16 CONTAINER. ĐANG TỰ ĐỘNG KHỞI ĐỘNG..."
    echo "========================================================================="
    docker compose -p cuonghauminicloud up -d
    bash object-storage-server/init-buckets.sh 2>/dev/null || true
  fi

  while true; do
    up_count=$(docker compose -p cuonghauminicloud ps -q 2>/dev/null | wc -l)
    if [ "$up_count" -ge 16 ]; then
      break
    fi
    printf "\r>>> Đang chờ đủ 16 Container: %d/16 Up... " "$up_count"
    sleep 1.5
  done
  return 0
}

step1_ps() {
  ensure_docker
  echo ""
  echo "========================================================================="
  echo " [BƯỚC 1] KIỂM TRA TRẠNG THÁI 16 CONTAINER (MẠNG CLOUD-NET 10.10.10.0/24)"
  echo "========================================================================="
  docker compose -p cuonghauminicloud ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
  echo "========================================================================="
  echo ""
}

step2_ping() {
  ensure_docker
  echo ""
  echo "========================================================================="
  echo " [BƯỚC 2] PING THÔNG MẠNG TỪ PROXY TỚI 9 CONTAINER NỘI BỘ (0% RỚT GÓI)"
  echo "========================================================================="
  bash scripts/ping-all.sh
  echo "========================================================================="
  echo ""
}

step3_api_db() {
  ensure_docker
  echo ""
  echo "========================================================================="
  echo " [BƯỚC 3] TEST API BACKEND FLASK & TRUY VẤN DATABASE MARIADB"
  echo "========================================================================="
  echo ">>> 1. Gọi API /hello trực tiếp (cổng $APP_PORT) và qua Proxy Gateway (cổng $PROXY_PORT):"
  printf "Direct  :$APP_PORT/hello -> "
  curl -s http://localhost:$APP_PORT/hello
  echo ""
  printf "Gateway :$PROXY_PORT/api/hello -> "
  curl -s http://localhost:$PROXY_PORT/api/hello
  echo ""
  echo ""
  echo ">>> 2. Truy vấn dữ liệu bảng 'notes' trong database MariaDB:"
  docker exec relational-database-server mariadb -uroot -p"$DB_ROOT_PASSWORD" -e "USE minicloud; SHOW TABLES; SELECT * FROM notes;"
  echo "========================================================================="
  echo ""
}

step4_dns() {
  ensure_docker
  echo ""
  echo "========================================================================="
  echo " [BƯỚC 4] PHÂN GIẢI TÊN MIỀN NỘI BỘ QUA MÁY CHỦ DNS BIND9 (CỔNG $DNS_PORT)"
  echo "========================================================================="
  echo ">>> Lệnh: dig @127.0.0.1 -p $DNS_PORT web-frontend-server.cloud.local +short"
  if docker info --format '{{.OperatingSystem}}' 2>/dev/null | grep -q 'Docker Desktop'; then
    docker run --rm --add-host host.docker.internal:host-gateway "$NETSHOOT" dig @host.docker.internal -p "$DNS_PORT" web-frontend-server.cloud.local +short
  else
    docker run --rm --network host "$NETSHOOT" dig @127.0.0.1 -p "$DNS_PORT" web-frontend-server.cloud.local +short
  fi
  echo ">>> Kết quả phân giải đúng IP tĩnh 10.10.10.10 của web-frontend-server!"
  echo "========================================================================="
  echo ""
}

step5_lb() {
  ensure_docker
  echo ""
  echo "========================================================================="
  echo " [BƯỚC 5] CÂN BẰNG TẢI ROUND ROBIN & DỪNG WEB2 FAILOVER TRONG 2 GIÂY"
  echo "========================================================================="
  bash scripts/lb-test.sh
  echo "========================================================================="
  echo ""
}

step6_smoke() {
  ensure_docker
  echo ""
  echo "========================================================================="
  echo " [BƯỚC 6] CHẠY BỘ SMOKE TEST TỰ ĐỘNG TOÀN DIỆN (32 / 32 TEST CASE PASS)"
  echo "========================================================================="
  bash scripts/smoke-test.sh local
  echo "========================================================================="
  echo ""
}

wait_step() {
  local step_num="$1"
  local next_name="$2"
  while true; do
    echo "-------------------------------------------------------------------------"
    echo ">>> [Bước $step_num/6 XONG] Các phím điều khiển:"
    echo "    - Bấm [ENTER] : Tiếp tục sang $next_name"
    echo "    - Gõ  [R]     : Quét lại / Chạy lại bước này (Re-check)"
    echo "    - Gõ  [Q]     : Dừng demo và quay về Menu chính"
    read -r -p ">>> Lựa chọn của bạn [Enter/R/Q]: " choice
    case "$choice" in
      [rR]) return 1 ;;  # Chạy lại bước này
      [qQ]) return 2 ;;  # Thoát về menu
      *)    return 0 ;;  # Sang bước tiếp theo
    esac
  done
}

step_all() {
  ensure_docker

  echo ""
  echo "========================================================================="
  echo "    BẮT ĐẦU CHẠY LIVE DEMO TUẦN TỰ TỪ A ĐẾN Z CHO HỆ THỐNG MYMINICLOUD   "
  echo "========================================================================="

  # BƯỚC 1
  while true; do
    step1_ps
    wait_step "1" "Bước 2 (Ping toàn mạng)"
    ret=$?
    if [ $ret -eq 0 ]; then break
    elif [ $ret -eq 2 ]; then return 0; fi
  done

  # BƯỚC 2
  while true; do
    step2_ping
    wait_step "2" "Bước 3 (Test API & MariaDB)"
    ret=$?
    if [ $ret -eq 0 ]; then break
    elif [ $ret -eq 2 ]; then return 0; fi
  done

  # BƯỚC 3
  while true; do
    step3_api_db
    wait_step "3" "Bước 4 (Phân giải DNS BIND9)"
    ret=$?
    if [ $ret -eq 0 ]; then break
    elif [ $ret -eq 2 ]; then return 0; fi
  done

  # BƯỚC 4
  while true; do
    step4_dns
    wait_step "4" "Bước 5 (Cân bằng tải & Failover 2s)"
    ret=$?
    if [ $ret -eq 0 ]; then break
    elif [ $ret -eq 2 ]; then return 0; fi
  done

  # BƯỚC 5
  while true; do
    step5_lb
    wait_step "5" "Bước 6 (Chạy 32 bài Smoke Test)"
    ret=$?
    if [ $ret -eq 0 ]; then break
    elif [ $ret -eq 2 ]; then return 0; fi
  done

  # BƯỚC 6
  while true; do
    step6_smoke
    echo "========================================================================="
    echo "  🎉 CHÚC MỪNG: HOÀN TẤT TOÀN BỘ 6 BƯỚC DEMO TRỰC TIẾP CỦA MYMINICLOUD!  "
    echo "========================================================================="
    break
  done
}

case "${1:-all}" in
  1|ps) step1_ps ;;
  2|ping) step2_ping ;;
  3|api|db) step3_api_db ;;
  4|dns) step4_dns ;;
  5|lb|failover) step5_lb ;;
  6|smoke) step6_smoke ;;
  all) step_all ;;
  *) echo "Cách dùng: $0 [1|2|3|4|5|6|all]" ;;
esac
