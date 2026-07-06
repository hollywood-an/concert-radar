import { NextRequest, NextResponse } from "next/server";

// Spotify redirects the browser here; we complete the exchange against the gateway
// and hand the minted session to the settings page via query params (dev-grade flow).
const GATEWAY_URL =
  process.env.GATEWAY_URL ?? process.env.NEXT_PUBLIC_GATEWAY_URL ?? "http://localhost:8000";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const code = request.nextUrl.searchParams.get("code");
  const state = request.nextUrl.searchParams.get("state");
  const settingsUrl = new URL("/settings", request.nextUrl.origin);

  if (code === null || state === null) {
    settingsUrl.searchParams.set("spotify_error", "missing code");
    return NextResponse.redirect(settingsUrl);
  }

  const params = new URLSearchParams({ code, state });
  const response = await fetch(`${GATEWAY_URL}/auth/spotify/callback?${params.toString()}`);
  if (!response.ok) {
    settingsUrl.searchParams.set("spotify_error", String(response.status));
    return NextResponse.redirect(settingsUrl);
  }

  const body = (await response.json()) as { token: string; imported_artists: number };
  settingsUrl.searchParams.set("token", body.token);
  settingsUrl.searchParams.set("imported", String(body.imported_artists));
  return NextResponse.redirect(settingsUrl);
}
