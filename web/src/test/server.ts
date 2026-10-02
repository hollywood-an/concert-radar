import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import type { DevAuthResponse, FeedPage } from "@/types";
import { user } from "@/test/fixtures";

// Must match NEXT_PUBLIC_GATEWAY_URL in vitest.config.mts.
export const GATEWAY_URL = "http://gateway.test";

export const TOKEN = "test-token";

export const EMPTY_PAGE: FeedPage = { items: [], next_cursor: null, has_more: false };

export const server = setupServer(
  http.post(`${GATEWAY_URL}/auth/dev`, () =>
    HttpResponse.json<DevAuthResponse>({ token: TOKEN, user }),
  ),
);
