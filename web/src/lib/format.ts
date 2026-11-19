// The year appears only when the show is not in the current calendar year, so a listing
// eleven months out ("Oct 15, 2027") can't be mistaken for last month.
export function formatDate(iso: string, now: Date = new Date()): string {
  const date = new Date(iso);
  return date.toLocaleString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: date.getFullYear() === now.getFullYear() ? undefined : "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

// The feed score as a whole-number match, or null when the user follows nobody: without
// follows there is no taste to match against and every show scores the same.
export function formatMatch(score: number, followCount: number): string | null {
  if (followCount === 0) {
    return null;
  }
  return `${Math.round(Math.min(Math.max(score, 0), 1) * 100)}% match`;
}

export function formatLongDate(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function formatDistance(meters: number): string {
  const miles = meters / 1609.34;
  return miles < 0.1 ? "nearby" : `${miles.toFixed(1)} mi`;
}

export function formatPrice(
  minCents: number | null,
  maxCents: number | null,
): string | null {
  if (minCents === null && maxCents === null) {
    return null;
  }
  const dollars = (cents: number) => `$${(cents / 100).toFixed(0)}`;
  if (minCents !== null && maxCents !== null && minCents !== maxCents) {
    return `${dollars(minCents)}–${dollars(maxCents)}`;
  }
  return dollars(minCents ?? maxCents ?? 0);
}
