export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
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
