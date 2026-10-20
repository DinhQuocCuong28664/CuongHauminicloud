// k6 load test scenarios for MyMiniCloud. Pick one with the SCENARIO variable; run them through scripts/loadtest/run.sh.
//   web       : 20 virtual users load the home page through the gateway for 30 seconds (web pool + load balancer)
//   failover  : like web but 60 seconds; run.sh stops web2 at second 20 and starts it again at second 40
//   ratelimit : a steady 30 requests/s to /api/hello from one IP for 20 seconds (gateway limit: 10/s, burst 20)
//   api       : 20 virtual users call the application server directly (no gateway, no rate limit):
//               /hello (no DB access) and /students-db (reads MariaDB)
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
  // 429 is the expected result of the ratelimit scenario, not an error. Per-endpoint thresholds give the summary separate numbers.
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
