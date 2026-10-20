// Kịch bản kiểm thử tải k6 cho MyMiniCloud. Chọn kịch bản bằng biến SCENARIO, chạy qua scripts/loadtest/run.sh.
//   web       : 20 người dùng ảo tải trang chủ qua gateway trong 30 giây (đo khả năng của cụm web + cân bằng tải)
//   failover  : như web nhưng 60 giây; run.sh dừng web2 ở giây 20 và bật lại ở giây 40
//   ratelimit : bắn đều 30 request/giây vào /api/hello từ một IP trong 20 giây (ngưỡng gateway: 10/giây, dồn 20)
//   api       : 20 người dùng ảo gọi thẳng application server (không qua gateway, không bị rate limit):
//               /hello (không chạm DB) và /students-db (đọc MariaDB)
import http from 'k6/http';
import { check } from 'k6';

const GATEWAY = __ENV.GATEWAY || 'http://api-gateway-proxy-server';
const APP = __ENV.APP || 'http://application-backend-server:8081';
const SCENARIO = __ENV.SCENARIO || 'web';
const OUT = __ENV.OUT || `/scripts/out/${SCENARIO}.json`;

const scenarios = {
  web: { executor: 'constant-vus', vus: 20, duration: '30s' },
  failover: { executor: 'constant-vus', vus: 20, duration: '60s' },
  ratelimit: { executor: 'constant-arrival-rate', rate: 30, timeUnit: '1s', duration: '20s', preAllocatedVUs: 10 },
  api: { executor: 'constant-vus', vus: 20, duration: '30s' },
};

export const options = {
  scenarios: { [SCENARIO]: scenarios[SCENARIO] },
  // 429 là kết quả mong đợi của kịch bản ratelimit, không tính là lỗi. Ngưỡng theo từng endpoint để summary có số liệu riêng.
  thresholds: SCENARIO === 'ratelimit' ? {} : {
    http_req_failed: ['rate<0.01'],
    ...(SCENARIO === 'api' ? {
      'http_req_duration{name:GET /hello}': ['p(95)<1000'],
      'http_req_duration{name:GET /students-db}': ['p(95)<1000'],
    } : {}),
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
  insecureSkipTLSVerify: false,
};

export default function () {
  if (SCENARIO === 'web' || SCENARIO === 'failover') {
    const r = http.get(`${GATEWAY}/`, { tags: { name: 'GET /' } });
    check(r, {
      'status 200': (x) => x.status === 200,
      'served by web1': (x) => x.headers['X-Served-By'] === 'web1',
      'served by web2': (x) => x.headers['X-Served-By'] === 'web2',
    });
  } else if (SCENARIO === 'ratelimit') {
    http.setResponseCallback(http.expectedStatuses(200, 429));
    const r = http.get(`${GATEWAY}/api/hello`, { tags: { name: 'GET /api/hello' } });
    check(r, { 'status 200': (x) => x.status === 200, 'status 429': (x) => x.status === 429 });
  } else if (SCENARIO === 'api') {
    const a = http.get(`${APP}/hello`, { tags: { name: 'GET /hello' } });
    const b = http.get(`${APP}/students-db`, { tags: { name: 'GET /students-db' } });
    check(a, { 'hello 200': (x) => x.status === 200 });
    check(b, { 'students-db 200': (x) => x.status === 200 });
  }
}

export function handleSummary(data) {
  return { [OUT]: JSON.stringify(data, null, 1) };
}
