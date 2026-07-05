// Typed fetch wrapper for the gateway API.

import type { ArtistSummary, DevAuthResponse, FeedPage } from "@/types";

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

export function getFeed(
  token: string,
  cursor: string | null,
  limit = 20,
): Promise<FeedPage> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor !== null) {
    params.set("cursor", cursor);
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
