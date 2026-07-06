// Typed fetch wrapper for the gateway API.

import type {
  ArtistSummary,
  DevAuthResponse,
  FeedFilters,
  FeedPage,
  User,
  UserUpdate,
} from "@/types";

const BASE_URL = process.env.NEXT_PUBLIC_GATEWAY_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (token !== undefined) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(`${BASE_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    throw new ApiError(
      response.status,
      `${options.method ?? "GET"} ${path} failed with ${response.status}`,
    );
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function devLogin(email: string): Promise<DevAuthResponse> {
  return request<DevAuthResponse>("/auth/dev", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export function getMe(token: string): Promise<User> {
  return request<User>("/me", {}, token);
}

export function patchMe(token: string, update: UserUpdate): Promise<User> {
  return request<User>("/me", { method: "PATCH", body: JSON.stringify(update) }, token);
}

export function getFeed(
  token: string,
  cursor: string | null,
  filters: FeedFilters,
  limit = 20,
): Promise<FeedPage> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor !== null) {
    params.set("cursor", cursor);
  }
  if (filters.dateRange !== null) {
    params.set("date_from", `${filters.dateRange[0]}T00:00:00Z`);
    params.set("date_to", `${filters.dateRange[1]}T23:59:59Z`);
  }
  if (filters.maxDistance !== null) {
    params.set("max_distance_m", String(filters.maxDistance));
  }
  if (filters.maxPrice !== null) {
    params.set("max_price_cents", String(filters.maxPrice));
  }
  for (const genre of filters.genres) {
    params.append("genres", genre);
  }
  return request<FeedPage>(`/feed?${params.toString()}`, {}, token);
}

export function searchArtists(token: string, q: string): Promise<ArtistSummary[]> {
  const params = new URLSearchParams({ q });
  return request<ArtistSummary[]>(`/artists/search?${params.toString()}`, {}, token);
}

export function listFollows(token: string): Promise<ArtistSummary[]> {
  return request<ArtistSummary[]>("/follows", {}, token);
}

export function followArtist(token: string, artistId: string): Promise<ArtistSummary> {
  return request<ArtistSummary>(
    "/follows",
    { method: "POST", body: JSON.stringify({ artist_id: artistId }) },
    token,
  );
}

export function unfollowArtist(token: string, artistId: string): Promise<void> {
  return request<void>(`/follows/${artistId}`, { method: "DELETE" }, token);
}

export function dismissEvent(token: string, eventId: string): Promise<void> {
  return request<void>(`/events/${eventId}/dismiss`, { method: "POST" }, token);
}

export function spotifyLogin(token: string): Promise<{ authorize_url: string }> {
  return request<{ authorize_url: string }>("/auth/spotify", { method: "POST" }, token);
}

export function feedSocketUrl(token: string): string {
  const ws = BASE_URL.replace(/^http/, "ws");
  return `${ws}/ws/feed?token=${encodeURIComponent(token)}`;
}
