import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { loadFollows, toggleFollow } from "@/store/followsSlice";
import type { AppStore } from "@/store/store";
import { artist, signedInStore } from "@/test/fixtures";
import { EMPTY_PAGE, GATEWAY_URL, server } from "@/test/server";

async function storeFollowing(artistIds: string[]): Promise<AppStore> {
  const store = await signedInStore();
  server.use(http.get(`${GATEWAY_URL}/follows`, () => HttpResponse.json(artistIds.map(artist))));
  await store.dispatch(loadFollows()).unwrap();
  return store;
}

// Records the follow writes and the feed re-rank; `ok: false` fails every write with a 500.
function serveGateway({ ok }: { ok: boolean }): string[] {
  const calls: string[] = [];
  server.use(
    http.post(`${GATEWAY_URL}/follows`, async ({ request }) => {
      const { artist_id } = (await request.json()) as { artist_id: string };
      calls.push(`POST /follows ${artist_id}`);
      return ok
        ? HttpResponse.json(artist(artist_id), { status: 201 })
        : new HttpResponse(null, { status: 500 });
    }),
    http.delete(`${GATEWAY_URL}/follows/:artistId`, ({ params }) => {
      calls.push(`DELETE /follows/${String(params.artistId)}`);
      return new HttpResponse(null, { status: ok ? 204 : 500 });
    }),
    http.get(`${GATEWAY_URL}/feed`, () => {
      calls.push("GET /feed");
      return HttpResponse.json(EMPTY_PAGE);
    }),
  );
  return calls;
}

// What EventCard and ArtistSearchBar do on click: pass the pre-click state from the store.
function clickFollow(store: AppStore, artistId: string) {
  const followed = store.getState().follows.artistIds.includes(artistId);
  return store.dispatch(toggleFollow({ artistId, followed }));
}

describe("toggleFollow", () => {
  it("follows an unfollowed artist with POST /follows, then re-ranks the feed", async () => {
    const store = await storeFollowing([]);
    const calls = serveGateway({ ok: true });

    const toggle = clickFollow(store, "a1");
    expect(store.getState().follows).toEqual({ artistIds: ["a1"], pendingToggles: ["a1"] });
    await toggle.unwrap();

    expect(store.getState().follows).toEqual({ artistIds: ["a1"], pendingToggles: [] });
    await vi.waitFor(() => expect(calls).toEqual(["POST /follows a1", "GET /feed"]));
  });

  it("unfollows a followed artist with DELETE /follows/:id, then re-ranks the feed", async () => {
    const store = await storeFollowing(["a1", "a2"]);
    const calls = serveGateway({ ok: true });

    const toggle = clickFollow(store, "a1");
    expect(store.getState().follows).toEqual({ artistIds: ["a2"], pendingToggles: ["a1"] });
    await toggle.unwrap();

    expect(store.getState().follows).toEqual({ artistIds: ["a2"], pendingToggles: [] });
    await vi.waitFor(() => expect(calls).toEqual(["DELETE /follows/a1", "GET /feed"]));
  });

  it("reverts an optimistic follow when the request fails", async () => {
    const store = await storeFollowing([]);
    const calls = serveGateway({ ok: false });

    const result = await clickFollow(store, "a1");

    expect(result.meta.requestStatus).toBe("rejected");
    expect(store.getState().follows).toEqual({ artistIds: [], pendingToggles: [] });
    expect(calls).toEqual(["POST /follows a1"]);
  });

  it("reverts an optimistic unfollow when the request fails", async () => {
    const store = await storeFollowing(["a1"]);
    const calls = serveGateway({ ok: false });

    const result = await clickFollow(store, "a1");

    expect(result.meta.requestStatus).toBe("rejected");
    expect(store.getState().follows).toEqual({ artistIds: ["a1"], pendingToggles: [] });
    expect(calls).toEqual(["DELETE /follows/a1"]);
  });
});
