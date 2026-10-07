// k6 load test for GET /feed, the most expensive read: a PostGIS radius join over upcoming
// shows, scored per request with the pgvector relevance function, then ranked and paged.
//
//   make loadtest                                     # local gateway (see Makefile)
//   make loadtest API_URL=https://api.<host>.sslip.io # the live deploy, over the internet
//
// Each virtual user signs in once in setup() as one of USERS demo accounts (loadtest-N@...).
import http from "k6/http";
import { check } from "k6";

const API = __ENV.API_URL || "http://localhost:8000";
const USERS = Number(__ENV.USERS || 10);

export const options = {
  scenarios: {
    feed: {
      executor: "constant-vus",
      vus: Number(__ENV.VUS || 20),
      duration: __ENV.DURATION || "30s",
    },
  },
  thresholds: {
    "http_req_duration{name:feed}": ["p(95)<200"],
    "http_req_failed{name:feed}": ["rate<0.01"],
  },
};

export function setup() {
  const tokens = [];
  for (let i = 0; i < USERS; i++) {
    const res = http.post(
      `${API}/auth/dev`,
      JSON.stringify({ email: `loadtest-${i}@example.com` }),
      { headers: { "Content-Type": "application/json" } },
    );
    if (res.status !== 200) {
      throw new Error(`sign-in failed with ${res.status}: ${res.body}`);
    }
    tokens.push(res.json("token"));
  }
  return { tokens };
}

export default function (data) {
  const token = data.tokens[(__VU - 1) % data.tokens.length];
  const res = http.get(`${API}/feed?limit=20`, {
    headers: { Authorization: `Bearer ${token}` },
    tags: { name: "feed" },
  });
  check(res, {
    "status is 200": (r) => r.status === 200,
    "returns a page of items": (r) => Array.isArray(r.json("items")),
  });
}
