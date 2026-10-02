import { login } from "@/store/authSlice";
import { makeStore, type AppStore } from "@/store/store";
import type { ArtistSummary, FeedItem, FeedPage, User } from "@/types";

export const user: User = {
  id: "user-1",
  email: "fan@example.com",
  display_name: "Fan",
  home_location: { lat: 37.7749, lon: -122.4194 },
  travel_radius_m: 40000,
  alert_email: true,
  created_at: "2026-01-01T00:00:00Z",
};

export function artist(id: string): ArtistSummary {
  return { id, name: `Artist ${id}`, image_url: null, genres: ["indie"], followed: true };
}

export function feedItem(eventId: string): FeedItem {
  return {
    event_id: eventId,
    title: `Show ${eventId}`,
    starts_at: "2026-11-01T20:00:00Z",
    status: "onsale",
    price_min_cents: 3500,
    price_max_cents: 6000,
    source_url: null,
    image_url: null,
    venue_name: "The Fillmore",
    venue_city: "San Francisco",
    venue_lat: 37.784,
    venue_lon: -122.433,
    distance_m: 1200,
    artist_id: "artist-1",
    artist_name: "Artist artist-1",
    artist_image_url: null,
    artist_genres: ["indie"],
    score: 0.9,
  };
}

export function feedPage(eventIds: string[], nextCursor: string | null): FeedPage {
  return {
    items: eventIds.map((id) => feedItem(id)),
    next_cursor: nextCursor,
    has_more: nextCursor !== null,
  };
}

// Signs in through the real login thunk against the default POST /auth/dev handler.
export async function signedInStore(): Promise<AppStore> {
  const store = makeStore();
  await store.dispatch(login(user.email)).unwrap();
  return store;
}
