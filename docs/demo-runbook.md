# Runbook demo MyMiniCloud (quay video và demo trước giảng viên)

Bám theo đề "Xây dựng mô phỏng hệ thống MiniCloud cơ bản". Thứ tự demo đi đúng cấu trúc chấm điểm:

| Phần | Nội dung | Điểm |
|---|---|---|
| A | Demo 9 server theo bảng "Yêu cầu demo & kiểm thử", rồi ping toàn mạng | 5 điểm (cơ bản) |
| B | 10 mục mở rộng, mỗi mục 0,5 điểm | 5 điểm |
| C | Phần nâng cao ngoài đề (A01–A12) | để nổi bật |
| D | Docker Hub và EC2 | yêu cầu kỹ thuật chung 4, 5 |

Tổng thời lượng gợi ý: 15–20 phút. Mỗi bước ghi rõ lệnh, chỗ cần mở trên trình duyệt, kết quả mong đợi và câu nói gợi ý.

**Bản rút gọn 8–10 phút (cho video nộp kèm báo cáo):**

| Thời gian | Làm gì | Mục chi tiết |
|---|---|---|
| 0:00–0:30 | Giới thiệu nhóm, `docker compose ps` (16 container) | 0 |
| 0:30–4:00 | A1–A9 nhanh: mỗi server một lệnh hoặc một tab, rồi `bash scripts/ping-all.sh` | A |
| 4:00–6:00 | Lướt bảng mục B: blog, `/api/student`, `/api/students-db`, token, MinIO 200/403, DNS, target `web`, dashboard System Health, `/student/`, round robin | B |
| 6:00–8:00 | Trang chủ: thanh CPU/RAM, thẻ trạng thái; dừng web2 thấy thẻ đỏ; Portal với `sv01` (thêm sinh viên) và `sv02` (bị 403) | C1, C2 |
| 8:00–9:30 | Docker Hub (tag `2.2`), ảnh EC2 trong báo cáo mục 4.8, `logs/smoke-local.txt` 32/32 | D, C6 |

Nhớ `docker start web-frontend-server2` sau đoạn 6:00–8:00.

> Mật khẩu nằm trong `.env`, không đọc to và không để lộ trên màn hình. Các bảng dưới đây chỉ ghi **tên biến**.

---

## 0. Chuẩn bị (trước khi bấm quay, khoảng 10 phút)

**Máy và Docker**
1. Bật Docker Desktop, đợi biểu tượng chuyển xanh.
2. Tắt các container của project khác (cổng 80, 3000, 9090… phải trống):
   ```bash
   docker ps --format '{{.Names}}'
   ```
3. Khởi động cụm và đợi mọi container healthy (Keycloak mất khoảng 1 phút):
   ```bash
   cd ~/DinhQuocCuong_CloudComputing/CuongHauminicloud
   docker compose up -d
   docker compose ps
   ```
   Kết quả mong đợi: 16 container `Up`, 14 container ghi `(healthy)`. Loki và web-frontend-exporter không có healthcheck nên không ghi `(healthy)`, đó là bình thường.
4. Chạy thử một lần toàn bộ test để chắc mọi thứ ổn (khoảng 5 phút; nên chạy trước khi quay):
   ```bash
   bash scripts/smoke-test.sh local
   ```
   Dòng cuối phải là `Tổng kết: 32 PASS, 0 FAIL`.
5. Nếu vừa build lại web server: chờ khoảng 5 phút cho cảnh báo giả `WebServerDown` tự resolved (xem mục Sự cố).

**Terminal:** dùng Windows Terminal (PowerShell hoặc Git Bash), cỡ chữ lớn (Ctrl + +).
- Lệnh có `docker exec -it` nên chạy trong PowerShell. Trong Git Bash phải thêm `winpty` ở đầu lệnh.

**Trình duyệt:** mở sẵn các tab, đúng thứ tự demo:

| Tab | Địa chỉ |
|---|---|
| 1 | http://localhost:18080/ (web1 trực tiếp) |
| 2 | http://localhost/ (qua gateway) |
| 3 | http://localhost:8081/auth/admin/ (Keycloak) |
| 4 | http://localhost:9001 (MinIO Console) |
| 5 | http://localhost:9090/targets (Prometheus) |
| 6 | http://localhost:3000 (Grafana) |
| 7 | http://localhost/portal/ |
| 8 | https://hub.docker.com/u/dinhquoccuong286 (Docker Hub) |

**Tài khoản (giá trị nằm trong `.env`):**

| Dịch vụ | Tài khoản | Mật khẩu |
|---|---|---|
| Keycloak admin | `KC_ADMIN` | `KC_ADMIN_PASSWORD` |
| MinIO | `MINIO_ROOT_USER` | `MINIO_ROOT_PASSWORD` |
| Grafana | `GF_ADMIN_USER` | `GF_ADMIN_PASSWORD` |
| Portal | `sv01` (editor), `sv02` (viewer) | `SV_PASSWORD` |
| MariaDB | `root` | `DB_ROOT_PASSWORD` |

Đăng nhập sẵn Keycloak, MinIO, Grafana ở các tab trước khi quay để khỏi gõ mật khẩu trên hình.

**Cổng khác đề trên máy này:** web1 dùng `18080` thay cho `8080` (cổng 8080 bị MiniTool ShadowMaker chiếm), MariaDB dùng `13306` thay cho `3306` (MySQL trong WSL). Nói rõ điều này khi demo; trên EC2 vẫn dùng đúng 8080 và 3306.

**Mở đầu video (30 giây):** giới thiệu nhóm, đề tài, rồi chạy `docker compose ps` để thấy toàn bộ container và mạng `cloud-net`.

---

## A. Demo 9 server theo đề (khoảng 6 phút)

### A1. Web Server (nginx) — trang chủ và /blog/
```bash
curl -I http://localhost:18080/
curl -I http://localhost:18080/blog/
```
- **Kết quả:** cả hai trả `HTTP/1.1 200 OK`, có header `X-Served-By: web1`.
- **Trình duyệt:** tab 1 (trang chủ "MyMiniCloud – Home") rồi bấm Blog ("MyMiniCloud – Blog").
- **Nói:** "Web server là nginx phục vụ trang tĩnh, có hai bản web1 và web2 cùng image."

### A2. Application Server (Flask) — /hello trực tiếp và qua proxy
```bash
curl http://localhost:8085/hello
curl http://localhost/api/hello
```
- **Kết quả:** hai lệnh trả cùng `{"message":"Hello from App Server!"}`.

### A3. Database (MariaDB)
```powershell
docker exec -it relational-database-server mariadb -uroot -p -e "SHOW DATABASES; SELECT * FROM minicloud.notes;"
```
- **Thao tác:** nhập mật khẩu `DB_ROOT_PASSWORD` khi được hỏi (ký tự không hiện ra màn hình).
- **Kết quả:** có các database `minicloud`, `studentdb`, `ops`; bảng `notes` có dòng "Hello from MariaDB!".

### A4. Authentication Server (Keycloak)
- **Trình duyệt:** tab 3, đã đăng nhập admin.
- **Thao tác:** Users → Add user → tạo `sv-demo` → Create.
- **Kết quả:** user mới xuất hiện trong danh sách.
- **Nói:** "Keycloak chạy dưới đường dẫn `/auth` để đi được qua reverse proxy."

### A5. Storage Server (MinIO)
- **Trình duyệt:** tab 4 → bucket `demo` → thấy `index.html`.
- **Thêm nếu muốn:** Upload thêm một file bất kỳ rồi tải về.

### A6. DNS Server (BIND9)
```bash
docker exec internal-dns-server dig @127.0.0.1 web-frontend-server.cloud.local +short
```
- **Kết quả:** `10.10.10.10`, là IP thật của web1 trong `cloud-net`.

### A7. Monitoring (Prometheus + Node Exporter)
- **Trình duyệt:** tab 5, các target đều `UP`, trong đó có `node` (monitoring-node-exporter-server:9100).
- **Thao tác:** vào Query, chạy `node_cpu_seconds_total` → Graph.

### A8. Grafana
- **Trình duyệt:** tab 6 → Dashboards → **Node Exporter Full**.
- **Kết quả:** biểu đồ CPU, RAM, Network có số liệu.
- **Nói:** "Datasource và dashboard được provisioning sẵn từ file, không thêm tay."

### A9. Reverse Proxy
```bash
curl -I http://localhost/
curl -s http://localhost/api/hello
curl -I http://localhost/auth/
```
- **Kết quả:** `200`, JSON của app, `302` chuyển tới trang đăng nhập Keycloak.
- **Nói:** "Ảnh mẫu của đề trả 404 ở `/auth/`; hệ thống của nhóm trả đúng 302."

### A10. Ping toàn mạng
```bash
bash scripts/ping-all.sh
```
- **Kết quả:** ping từ trong proxy tới 9 server theo tên, `0% packet loss`, độ trễ dưới 1 ms.
- **Nói:** "Đến đây là xong phần cơ bản 5 điểm."

---

## B. 10 mục mở rộng (khoảng 5 phút)

| Mục | Demo | Kết quả cần thấy |
|---|---|---|
| E01 Blog | http://localhost/blog/ → mở 1–2 bài | 6 bài (3 theo đề + 3 thêm), mỗi bài có ảnh và link về trang chủ |
| E02 /student | http://localhost/api/student | bảng 5 sinh viên đọc từ `students.json` |
| E03 studentdb | http://localhost/api/students-db | bảng sinh viên đọc từ MariaDB `studentdb.students` |
| E04 Realm + token | `bash scripts/get-token.sh sv01` | token của realm `realm_523H0008_523H0025`; `/api/secure` trả 200 khi có token, 401 khi thiếu hoặc token bị sửa |
| E05 MinIO | http://localhost:9000/profile-pics/avatar.jpg và http://localhost:9000/documents/report.pdf | ảnh public trả 200; PDF private trả 403 (AccessDenied) |
| E06 DNS | `docker exec internal-dns-server dig @127.0.0.1 app-backend.cloud.local +short` (thêm `minio.cloud.local`, `keycloak.cloud.local`) | 10.10.10.20, 10.10.10.50, 10.10.10.40 |
| E07 Target web | tab 5 → job `web` | `UP` (nginx-prometheus-exporter, số liệu thật, không phải file tĩnh) |
| E08 Dashboard | Grafana → **System Health of 523H0008 & 523H0025** | CPU %, Memory, Network |
| E09 /student/ | `curl http://localhost/student/` | danh sách sinh viên JSON qua route mới của proxy |
| E10 Round robin | `bash scripts/lb-test.sh`, rồi trang chủ → khối "Cân bằng tải" | web1/web2 luân phiên; dừng web2 vẫn phục vụ bằng web1 |

**E05 presigned URL (nếu có thời gian):** dòng T-E05 trong `logs/smoke-local.txt` ghi lại link tải PDF bằng presigned URL (hết hạn sau 10 phút), trả 200.

**Kết thúc phần B:** "Nhóm hoàn thành 10/10 mục mở rộng, kiểm chứng tự động bằng 20 test case T-B và T-E."

---

## C. Phần nâng cao ngoài đề (khoảng 5 phút)

### C1. Trang chủ: bảng trạng thái trực tiếp (A12)
- **Trình duyệt:** tab 2. Chỉ cho thấy:
  - thanh tài nguyên trên cùng: CPU, RAM, số container, số cảnh báo (số thật lấy từ Prometheus và Alertmanager);
  - thẻ trạng thái của 9 loại server (logo, độ trễ, % sẵn sàng, dải 30 lần kiểm tra), tự làm mới mỗi 5 giây;
  - sơ đồ kiến trúc.
- **Thao tác:** dừng web2 ngay trong lúc quay:
  ```bash
  docker stop web-frontend-server2
  ```
- **Kết quả:** sau vài giây thẻ web2 viền đỏ, nhãn "Lỗi", dải lịch sử thêm vạch đỏ, ô web2 trên sơ đồ đổi màu, khối cân bằng tải chỉ còn web1. **Giữ web2 dừng** để dùng tiếp cho C3.

### C2. Portal (A01–A04)
Tab 7 → Đăng nhập bằng Keycloak với `sv01`.
- **Hồ sơ:** họ tên, role, issuer, thời hạn token; kéo thả một ảnh JPG/PNG → "Tải ảnh lên MinIO" → ảnh hiện ngay.
- **Sinh viên:**
  - thêm `SV010`: dòng mới nháy;
  - nhập mã sai (`X`): form rung và báo lỗi 400;
  - sửa, rồi xoá (có hộp xác nhận).
- **Tài liệu:** tải `report.pdf` private qua app.
- **Phân quyền:** đăng xuất, đăng nhập `sv02`, thử thêm sinh viên → bị từ chối 403. Nói: "Quyền được kiểm tra ở Flask, không chỉ ẩn nút trên giao diện."

### C3. Cảnh báo (A07)
- **Chờ:** sau khoảng 1 phút kể từ lúc dừng web2.
- **Trình duyệt:** Prometheus → Alerts: `WebServerDown` firing. Portal → Vận hành: cảnh báo hiện trong bảng.
- **Thao tác:** bật lại web2:
  ```bash
  docker start web-frontend-server2
  ```
  Khoảng 1 phút sau cảnh báo chuyển sang resolved.

### C4. Log tập trung (A05) và giám sát container (A06)
- **Log (A05):** trong Portal, mục "Nhật ký gọi API", copy một `request_id` → Grafana → dashboard **Logs – MyMiniCloud (Loki)** → dán vào ô `request_id` → thấy cùng request ở log của proxy và của app.
- **Container (A06):** dashboard **Containers – MyMiniCloud (cAdvisor)** (CPU/RAM từng container) và **API – RED metrics**.

### C5. Gateway (A08), sao lưu (A09), DNS cho app (A10)
```bash
seq 1 40 | xargs -P 20 -I{} curl -s -o /dev/null -w '%{http_code}\n' http://localhost/api/hello | sort | uniq -c
docker compose --profile ops run --rm db-backup
docker compose --profile ops run --rm --entrypoint python db-backup /app/restore.py
docker exec application-backend-server getent hosts db.cloud.local
```
- **Kết quả:**
  - rate limit: phần vượt ngưỡng trả `429`;
  - sao lưu: bản gzip lên bucket `db-backups`; khôi phục thử thì checksum khớp bản gốc;
  - DNS: app phân giải `db.cloud.local` qua BIND9.
- **Lưu ý trong Git Bash:** lệnh đầu có `/dev/null`. Nếu curl báo lỗi ghi file, thay `/dev/null` bằng `NUL`.

### C6. Kiểm thử tự động
```bash
bash scripts/smoke-test.sh local
```
- **Lưu ý:** không cần chạy lại trên hình vì mất khoảng 5 phút. Mở `logs/smoke-local.txt` và cuộn tới dòng `Tổng kết: 32 PASS, 0 FAIL`.

---

## D. Docker Hub và AWS EC2 (khoảng 2 phút)

### D1. Docker Hub
- **Trình duyệt:** tab 8. Có `myminicloud-web`, `myminicloud-app`, `myminicloud-proxy`, `myminicloud-db-backup`, mỗi image có tag `2.2` và `latest`.

### D2. EC2: chọn một trong hai cách
**Cách 1 — dùng minh chứng có sẵn (khuyên dùng, không tốn tiền):** mở trong báo cáo mục 4.8 các ảnh EC2:
- trang chủ qua `https://<ip>.sslip.io`;
- chứng chỉ Let's Encrypt;
- smoke test 32/32 trên EC2;
- Security Group.

**Cách 2 — chạy thật (tài khoản B, khoảng 10–15 phút, máy t3.medium tính tiền theo giờ, trừ vào tín dụng):**
```bash
bash scripts/ec2/launch.sh      # bật lại instance, ghi IP mới vào scripts/ec2/instance.env
bash scripts/ec2/deploy.sh      # đẩy cấu hình, pull image, xin chứng chỉ HTTPS cho <ip>.sslip.io
bash scripts/ec2/remote-check.sh
bash scripts/ec2/stop.sh        # BẮT BUỘC: dừng máy sau khi demo
```
- **Lưu ý:**
  - Public IP đổi sau mỗi lần bật lại máy.
  - Nếu đổi mạng (ở trường, ở nhà), `launch.sh` sẽ thêm luật Security Group cho IP mới.
  - EC2 kéo image theo `IMAGE_TAG` trong `.env` (hiện là `2.2`), nên phải push image lên Docker Hub trước khi deploy.

---

## E. Sự cố thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Grafana (http://localhost:3000) không vào được | Container bị dừng bằng tay trước đó, `restart: unless-stopped` không tự bật lại | `docker compose up -d monitoring-grafana-dashboard-server` |
| Bind cổng lỗi "forbidden by its access permissions" | Hyper-V giữ dải cổng | `netsh interface ipv4 show excludedportrange protocol=tcp`, đổi cổng trong `.env` |
| Vừa build lại web1/web2 thì có cảnh báo `WebServerDown` cho cả hai | cAdvisor còn giữ số liệu của container cũ vài phút | Chờ khoảng 5 phút cho tự resolved rồi mới demo C3 |
| Keycloak trả 502 hoặc trang trắng ngay sau `up -d` | Keycloak khởi động chậm (khoảng 1 phút) | Chờ `docker compose ps` báo `(healthy)` |
| Trang web vẫn là giao diện cũ sau khi build lại | Trình duyệt giữ cache | Ctrl + Shift + R |
| `docker exec -it` báo "the input device is not a TTY" | Đang chạy trong Git Bash | Dùng PowerShell, hoặc thêm `winpty` ở đầu lệnh |
| Portal báo "Phiên đăng nhập đã hết" | Refresh token hết hạn | Đăng nhập lại |

---

## F. Sau khi quay

1. Nếu đã chạy EC2: `bash scripts/ec2/stop.sh`, rồi kiểm tra instance ở trạng thái `stopped`.
2. Tắt cụm local khi không dùng (dữ liệu trong volume vẫn còn):
   ```bash
   docker compose stop
   ```
3. Dán link video vào Phụ lục A của báo cáo.
