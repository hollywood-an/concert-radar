import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import {
  ApiError,
  feedSocketUrl,
  geocode,
  getDiscover,
  getFeed,
  unfollowArtist,
} from "@/lib/api";
import { EMPTY_PAGE, GATEWAY_URL, server, TOKEN } from "@/test/server";
import type { FeedFilters } from "@/types";

const NO_FILTERS: FeedFilters = { dateRange: null, genres: [], maxDistance: null, maxPrice: null };

function serveFeed(): Request[] {
  const requests: Request[] = [];
  server.use(
    http.get(`${GATEWAY_URL}/feed`, ({ request }) => {
      requests.push(request);
      return HttpResponse.json(EMPTY_PAGE);
    }),
  );
  return requests;
}

describe("getFeed", () => {
  it("puts the cursor and every filter in the query string", async () => {
    const requests = serveFeed();

    await getFeed(
      TOKEN,
      "cursor-2",
      {
        dateRange: ["2026-10-01", "2026-10-31"],
        genres: ["indie rock", "jazz"],
        maxDistance: 16093.4,
        maxPrice: 5000,
      },
      50,
    );

    expect(requests).toHaveLength(1);
    const params = new URL(requests[0].url).searchParams;
    expect(params.get("limit")).toBe("50");
    expect(params.get("cursor")).toBe("cursor-2");
    expect(params.get("date_from")).toBe("2026-10-01T00:00:00Z");
    expect(params.get("date_to")).toBe("2026-10-31T23:59:59Z");
    expect(params.get("max_distance_m")).toBe("16093.4");
    expect(params.get("max_price_cents")).toBe("5000");
    expect(params.getAll("genres")).toEqual(["indie rock", "jazz"]);
  });

  it("sends only the default limit without a cursor or filters", async () => {
    const requests = serveFeed();

    await getFeed(TOKEN, null, NO_FILTERS);

    const params = new URL(requests[0].url).searchParams;
    expect(Array.from(params.keys())).toEqual(["limit"]);
    expect(params.get("limit")).toBe("20");
  });

  it("sends the bearer token", async () => {
    const requests = serveFeed();

    await getFeed(TOKEN, null, NO_FILTERS);

    expect(requests[0].headers.get("Authorization")).toBe(`Bearer ${TOKEN}`);
  });

  it("throws ApiError carrying the status code on a non-2xx response", async () => {
    server.use(http.get(`${GATEWAY_URL}/feed`, () => new HttpResponse(null, { status: 503 })));

    const error: unknown = await getFeed(TOKEN, null, NO_FILTERS).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 503 });
  });
});

describe("unfollowArtist", () => {
  it("resolves to undefined on 204 No Content", async () => {
    server.use(
      http.delete(
        `${GATEWAY_URL}/follows/:artistId`,
        () => new HttpResponse(null, { status: 204 }),
      ),
    );

    await expect(unfollowArtist(TOKEN, "artist-1")).resolves.toBeUndefined();
  });
});

describe("getDiscover", () => {
  it("asks for the default ten and surfaces a 503 as ApiError", async () => {
    const requests: Request[] = [];
    server.use(
      http.get(`${GATEWAY_URL}/discover`, ({ request }) => {
        requests.push(request);
        return new HttpResponse(null, { status: 503 });
      }),
    );

    const error: unknown = await getDiscover(TOKEN).catch((e: unknown) => e);

    expect(new URL(requests[0].url).searchParams.get("limit")).toBe("10");
    expect(error).toMatchObject({ status: 503 });
  });
});

describe("geocode", () => {
  it("sends the query and returns the places", async () => {
    const requests: Request[] = [];
    const places = [{ label: "Columbus, Ohio, United States", lat: 39.96, lon: -83.0 }];
    server.use(
      http.get(`${GATEWAY_URL}/geocode`, ({ request }) => {
        requests.push(request);
        return HttpResponse.json(places);
      }),
    );

    await expect(geocode(TOKEN, "Columbus, OH")).resolves.toEqual(places);
    expect(new URL(requests[0].url).searchParams.get("q")).toBe("Columbus, OH");
    expect(requests[0].headers.get("Authorization")).toBe(`Bearer ${TOKEN}`);
  });
});

describe("feedSocketUrl", () => {
  it("turns an http gateway into ws", () => {
    expect(feedSocketUrl("abc")).toBe("ws://gateway.test/ws/feed?token=abc");
  });

  it("turns an https gateway into wss", async () => {
    vi.stubEnv("NEXT_PUBLIC_GATEWAY_URL", "https://api.example.com");
    vi.resetModules();
    // api.ts reads the gateway URL at import, so load a fresh copy under the stubbed env.
    const api = await import("@/lib/api");

    expect(api.feedSocketUrl("abc")).toBe("wss://api.example.com/ws/feed?token=abc");
  });

  it("URL-encodes the token", () => {
    expect(feedSocketUrl("a+b/c=d e&f")).toBe(
      "ws://gateway.test/ws/feed?token=a%2Bb%2Fc%3Dd%20e%26f",
    );
  });
});
