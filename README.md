# MyMiniCloud — CuongHauminicloud

Đồ án cuối kỳ môn Điện toán đám mây: mô phỏng một cloud platform thu nhỏ gồm 9 loại server, mỗi server chạy trong một
container, nối chung mạng `cloud-net`, khởi động bằng `docker compose`.

Nhóm: **Đinh Quốc Cường – 523H0008**, **Nguyễn Cao Hậu – 523H0025**.

## Chạy nhanh

```bash
cp .env.example .env        # rồi đổi mật khẩu trong .env
docker compose build
docker compose up -d
docker compose ps
bash scripts/smoke-test.sh  # chạy toàn bộ kiểm thử, ghi log vào logs/
```

## Image trên Docker Hub

Ba image tự build (tag `1.0` và `latest`, public):

- https://hub.docker.com/r/dinhquoccuong286/myminicloud-web
- https://hub.docker.com/r/dinhquoccuong286/myminicloud-app
- https://hub.docker.com/r/dinhquoccuong286/myminicloud-proxy

Trên máy chỉ cần chạy (như EC2), đặt `DOCKERHUB_USER=dinhquoccuong286` trong `.env` rồi:

```bash
docker compose pull
docker compose up -d
```

## Triển khai trên AWS EC2 (tài khoản B, ap-southeast-1)

| Script | Việc |
|---|---|
| `scripts/ec2/launch.sh` | tạo key pair, security group (80 mở Internet; 22 và cổng quản trị chỉ My IP; không mở 3306, 9100, 1053), instance t3.medium Ubuntu 24.04, gp3 30 GB; `user-data.sh` cài Docker và swap 2 GB |
| `scripts/ec2/deploy.sh` | gửi mã nguồn + `.env` (PUBLIC_HOST = public IP), `docker compose pull` từ Docker Hub, `up -d --no-build`, chạy smoke test trên EC2 |
| `scripts/ec2/remote-check.sh` | kiểm thử từ máy cá nhân qua public IP, kể cả xác nhận cổng 3306/9100 bị chặn |
| `scripts/ec2/stop.sh` | Stop instance (không Terminate) khi không dùng |

Public IP đổi mỗi lần Stop/Start: chạy lại `launch.sh` (tự Start và ghi IP mới) rồi `deploy.sh`.

## Đường dẫn chính (qua reverse proxy, cổng 80)

| Đường dẫn | Đích | Ghi chú |
|---|---|---|
| `/`, `/blog/` | web1, web2 (round robin) | header `X-Served-By`, `X-Upstream-Addr` |
| `/api/hello`, `/api/notes` | App | `/notes` đọc `minicloud.notes` |
| `/api/student`, `/student/` | App | đọc `students.json` (mở rộng 2, 9) |
| `/api/students-db` | App → MariaDB | đọc `studentdb.students` (mở rộng 3) |
| `/api/secure` | App | cần Bearer token của realm `realm_523H0008_523H0025` (mở rộng 4) |
| `/auth/` | Keycloak | console quản trị, token endpoint |

## Script kiểm thử

| Script | Việc |
|---|---|
| `scripts/smoke-test.sh [nhãn]` | toàn bộ test case T-B01…T-B10, T-E01…T-E10 → `logs/smoke-<nhãn>.txt` |
| `scripts/ping-all.sh` | ping 9 server từ trong proxy → `evidence/ping-all.txt` |
| `scripts/get-token.sh [user]` | lấy token sv01/sv02, gọi `/api/secure` → `evidence/e04-token-<user>.txt` |
| `scripts/lb-test.sh` | round robin và failover khi dừng web2 → `evidence/e10-lb-test.txt` |
| `scripts/persistence-check.sh` | `compose down` rồi `up -d`, so sánh dữ liệu trong volume |
| `object-storage-server/init-buckets.sh` | tạo bucket `demo`, `profile-pics` (public), `documents` (private) |

## Contracts (thống nhất giữa các thành viên)

### Mạng `cloud-net` (10.10.10.0/24, gateway 10.10.10.1)

| Server | Container | IP | Alias ngắn | Cổng host → container | Phụ trách |
|---|---|---|---|---|---|
| 9. Reverse proxy / LB | `api-gateway-proxy-server` | 10.10.10.2 | `proxy` | `PROXY_PORT` 80 → 80 | Cường |
| 1. Web (bản 1) | `web-frontend-server1` | 10.10.10.10 | `web`, `web-frontend-server` | `WEB1_PORT` 8080 → 80 | Hậu |
| 1. Web (bản 2, cho LB) | `web-frontend-server2` | 10.10.10.11 | `web2` | `WEB2_PORT` 8088 → 80 | Hậu |
| 2. Application | `application-backend-server` | 10.10.10.20 | `app-server`, `app-backend` | `APP_PORT` 8085 → 8081 | Cường |
| 3. Database | `relational-database-server` | 10.10.10.30 | `db` | `DB_PORT` 3306 → 3306 | Hậu |
| 4. Authentication | `authentication-identity-server` | 10.10.10.40 | `keycloak` | `AUTH_PORT` 8081 → 8080 | Cường |
| 5. Object storage | `object-storage-server` | 10.10.10.50 | `minio` | 9000 (S3 API), 9001 (console) | Hậu |
| 6. DNS | `internal-dns-server` | 10.10.10.53 | `dns-server` | `DNS_PORT` 1053/udp → 53/udp | Hậu |
| 7. Monitoring | `monitoring-prometheus-server` | 10.10.10.60 | `prometheus` | 9090 | Hậu |
| 7. (phụ) Node Exporter | `monitoring-node-exporter-server` | 10.10.10.61 | `node-exporter` | 9100 | Hậu |
| 7. (phụ) Nginx exporter | `web-frontend-exporter` | 10.10.10.62 | — | không publish | Hậu |
| 8. Grafana | `monitoring-grafana-dashboard-server` | 10.10.10.70 | `grafana` | 3000 | Hậu |

### Biến môi trường (`.env`)

Xem `.env.example`. Tên biến cố định: `DB_ROOT_PASSWORD`, `DB_APP_USER`, `DB_APP_PASSWORD`, `KC_ADMIN`, `KC_ADMIN_PASSWORD`,
`KC_REALM`, `OIDC_CLIENT_ID`, `SV_PASSWORD`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `GF_ADMIN_USER`, `GF_ADMIN_PASSWORD`,
`PUBLIC_HOST`, `DOCKERHUB_USER`, `IMAGE_TAG` và các biến `*_PORT`.

### Phiên bản image (ghim cứng, kiểm tra ngày 2026-10-20)

| Image | Tag |
|---|---|
| nginx (web, proxy) | `1.30.6-alpine` (stable) |
| python (app) | `3.12-alpine` |
| mariadb | `11.4.13` (LTS) |
| quay.io/keycloak/keycloak | `26.8.1` |
| pgsty/minio, pgsty/mc | `RELEASE.2026-08-04T00-00-00Z`, `RELEASE.2026-10-18T00-00-00Z` (MinIO chính thức đã ngừng phát hành image; dùng bản fork cộng đồng còn đủ console) |
| internetsystemsconsortium/bind9 | `9.18` |
| prom/prometheus | `v3.15.0` |
| prom/node-exporter | `v1.12.1` |
| grafana/grafana | `13.2.4` |
| nginx/nginx-prometheus-exporter | `1.5.3` |
