# ADR 003: The gateway is the only API; no ORM in the web app

## Status

Accepted. Replaces the spec's "dual ORM strategy" (SQLAlchemy in Python, Drizzle in
Next.js API routes that proxy the gateway).

## Context

The spec had the Next.js app own a second data path: Drizzle ORM models mirroring the
Postgres schema and API routes that proxy the gateway. Every rule the feed depends on (radius,
dismissals, ranking, auth) would then exist in two languages, and every migration would need
a matching Drizzle change. The browser needs nothing the gateway cannot serve.

## Decision

The browser calls the FastAPI gateway directly (`web/src/lib/api.ts`, with
`NEXT_PUBLIC_GATEWAY_URL`), authenticated with the gateway's JWT, and receives live matches
over the gateway's WebSocket. The only Next.js API route is the Spotify OAuth callback, which
has to live on the web origin because Spotify redirects the browser there. There is no ORM in
the web app; schema and query logic live in one place.

## Consequences

- One source of truth for data access, auth, and ranking, all covered by the gateway's
  integration tests.
- The gateway must allow the web origin through CORS (`CORS_ORIGINS`), and the gateway URL is
  baked into the web build (it is a `NEXT_PUBLIC_` variable).
- No server-side rendering of personalized data: pages fetch after hydration. Acceptable for an
  app that is entirely behind sign-in.
