import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { loadSession } from "@/store/authSlice";
import { makeStore } from "@/store/store";
import { user } from "@/test/fixtures";
import { GATEWAY_URL, server, TOKEN } from "@/test/server";
import type { User } from "@/types";

const cachedUser: User = { ...user, display_name: "Cached name" };

function cacheSession(): void {
  localStorage.setItem("cr_token", TOKEN);
  localStorage.setItem("cr_user", JSON.stringify(cachedUser));
}

describe("loadSession", () => {
  it("refreshes the cached user from /me when the token is valid", async () => {
    cacheSession();
    const authHeaders: (string | null)[] = [];
    server.use(
      http.get(`${GATEWAY_URL}/me`, ({ request }) => {
        authHeaders.push(request.headers.get("Authorization"));
        return HttpResponse.json(user);
      }),
    );
    const store = makeStore();

    await store.dispatch(loadSession());

    expect(authHeaders).toEqual([`Bearer ${TOKEN}`]);
    expect(store.getState().auth).toEqual({ token: TOKEN, user, status: "authenticated" });
    expect(JSON.parse(localStorage.getItem("cr_user") ?? "null")).toEqual(user);
  });

  it("clears the stored session and stays signed out when /me rejects the token", async () => {
    cacheSession();
    server.use(http.get(`${GATEWAY_URL}/me`, () => new HttpResponse(null, { status: 401 })));
    const store = makeStore();

    await store.dispatch(loadSession());

    expect(localStorage.getItem("cr_token")).toBeNull();
    expect(localStorage.getItem("cr_user")).toBeNull();
    expect(store.getState().auth).toEqual({ token: null, user: null, status: "idle" });
  });

  it("keeps the cached session when the gateway is unreachable", async () => {
    cacheSession();
    server.use(http.get(`${GATEWAY_URL}/me`, () => HttpResponse.error()));
    const store = makeStore();

    await store.dispatch(loadSession());

    expect(store.getState().auth).toEqual({
      token: TOKEN,
      user: cachedUser,
      status: "authenticated",
    });
    expect(localStorage.getItem("cr_token")).toBe(TOKEN);
    expect(JSON.parse(localStorage.getItem("cr_user") ?? "null")).toEqual(cachedUser);
  });

  it("stays signed out without calling /me when nothing is stored", async () => {
    let meCalls = 0;
    server.use(
      http.get(`${GATEWAY_URL}/me`, () => {
        meCalls += 1;
        return HttpResponse.json(user);
      }),
    );
    const store = makeStore();

    await store.dispatch(loadSession());

    expect(meCalls).toBe(0);
    expect(store.getState().auth).toEqual({ token: null, user: null, status: "idle" });
  });
});
