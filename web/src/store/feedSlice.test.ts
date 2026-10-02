import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { dismissEvent, fetchFeedPage, filtersChanged, matchReceived } from "@/store/feedSlice";
import { makeStore, type AppStore } from "@/store/store";
import { feedItem, feedPage, signedInStore } from "@/test/fixtures";
import { GATEWAY_URL, server } from "@/test/server";
import type { FeedFilters, FeedPage } from "@/types";

function eventIds(store: AppStore): string[] {
  return store.getState().feed.items.map((item) => item.event_id);
}

// Serves the given pages in order and records the cursor each request asked for.
function serveFeedPages(...pages: FeedPage[]): (string | null)[] {
  const cursors: (string | null)[] = [];
  server.use(
    http.get(`${GATEWAY_URL}/feed`, ({ request }) => {
      cursors.push(new URL(request.url).searchParams.get("cursor"));
      const page = pages.shift();
      return page === undefined
        ? new HttpResponse(null, { status: 500 })
        : HttpResponse.json(page);
    }),
  );
  return cursors;
}

describe("fetchFeedPage", () => {
  it("loads the first page on reset and appends the next page from the cursor", async () => {
    const store = await signedInStore();
    const cursors = serveFeedPages(feedPage(["e1", "e2"], "c1"), feedPage(["e3"], null));

    await store.dispatch(fetchFeedPage({ reset: true })).unwrap();
    expect(eventIds(store)).toEqual(["e1", "e2"]);
    expect(store.getState().feed).toMatchObject({ cursor: "c1", hasMore: true, status: "idle" });

    await store.dispatch(fetchFeedPage({ reset: false })).unwrap();
    expect(eventIds(store)).toEqual(["e1", "e2", "e3"]);
    expect(store.getState().feed).toMatchObject({ cursor: null, hasMore: false, status: "idle" });

    expect(cursors).toEqual([null, "c1"]);
  });

  it("replaces the loaded pages and clears fresh markers on reset", async () => {
    const store = await signedInStore();
    const cursors = serveFeedPages(feedPage(["e1"], "c1"), feedPage(["e4"], "c2"));
    await store.dispatch(fetchFeedPage({ reset: true })).unwrap();
    store.dispatch(matchReceived(feedItem("e9")));

    await store.dispatch(fetchFeedPage({ reset: true })).unwrap();

    expect(eventIds(store)).toEqual(["e4"]);
    expect(store.getState().feed).toMatchObject({ cursor: "c2", freshEventIds: [] });
    expect(cursors).toEqual([null, null]);
  });
});

describe("matchReceived", () => {
  it("puts a new match at the top and marks it fresh", () => {
    const store = makeStore();
    store.dispatch(matchReceived(feedItem("e1")));

    store.dispatch(matchReceived(feedItem("e2")));

    expect(eventIds(store)).toEqual(["e2", "e1"]);
    expect(store.getState().feed.freshEventIds).toEqual(["e1", "e2"]);
  });

  it("ignores a match that is already in the feed", async () => {
    const store = await signedInStore();
    serveFeedPages(feedPage(["e1"], null));
    await store.dispatch(fetchFeedPage({ reset: true })).unwrap();
    store.dispatch(matchReceived(feedItem("e2")));

    store.dispatch(matchReceived(feedItem("e1")));
    store.dispatch(matchReceived(feedItem("e2")));

    expect(eventIds(store)).toEqual(["e2", "e1"]);
    expect(store.getState().feed.freshEventIds).toEqual(["e2"]);
  });
});

describe("dismissEvent", () => {
  it("removes the event once the gateway accepts the dismissal", async () => {
    const store = await signedInStore();
    const dismissed: string[] = [];
    server.use(
      http.post(`${GATEWAY_URL}/events/:eventId/dismiss`, ({ params }) => {
        dismissed.push(String(params.eventId));
        return new HttpResponse(null, { status: 204 });
      }),
    );
    store.dispatch(matchReceived(feedItem("e1")));
    store.dispatch(matchReceived(feedItem("e2")));

    await store.dispatch(dismissEvent("e1")).unwrap();

    expect(dismissed).toEqual(["e1"]);
    expect(eventIds(store)).toEqual(["e2"]);
    expect(store.getState().feed.freshEventIds).toEqual(["e2"]);
  });
});

describe("filtersChanged", () => {
  it("stores the filters and resets paging", async () => {
    const store = await signedInStore();
    serveFeedPages(feedPage(["e1", "e2"], "c1"));
    await store.dispatch(fetchFeedPage({ reset: true })).unwrap();
    store.dispatch(matchReceived(feedItem("e9")));
    const filters: FeedFilters = {
      dateRange: null,
      genres: ["jazz"],
      maxDistance: null,
      maxPrice: 5000,
    };

    store.dispatch(filtersChanged(filters));

    expect(store.getState().feed).toMatchObject({
      filters,
      items: [],
      cursor: null,
      hasMore: false,
      freshEventIds: [],
    });
  });
});
