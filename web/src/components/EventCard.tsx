"use client";

import type { FeedItem } from "@/types";
import FollowButton from "@/components/FollowButton";

interface EventCardProps {
  item: FeedItem;
  followed: boolean;
  pending: boolean;
  onToggleFollow: (artistId: string, followed: boolean) => void;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatDistance(meters: number): string {
  const miles = meters / 1609.34;
  return miles < 0.1 ? "nearby" : `${miles.toFixed(1)} mi`;
}

function formatPrice(minCents: number | null, maxCents: number | null): string | null {
  if (minCents === null && maxCents === null) {
    return null;
  }
  const dollars = (cents: number) => `$${(cents / 100).toFixed(0)}`;
  if (minCents !== null && maxCents !== null && minCents !== maxCents) {
    return `${dollars(minCents)}–${dollars(maxCents)}`;
  }
  return dollars(minCents ?? maxCents ?? 0);
}

const STATUS_STYLES: Record<string, string> = {
  on_sale: "bg-green-100 text-green-800",
  announced: "bg-amber-100 text-amber-800",
};

export default function EventCard({ item, followed, pending, onToggleFollow }: EventCardProps) {
  const price = formatPrice(item.price_min_cents, item.price_max_cents);
  return (
    <article className="flex gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      {item.image_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={item.image_url}
          alt=""
          className="h-24 w-24 flex-none rounded-lg object-cover"
        />
      ) : (
        <div className="flex h-24 w-24 flex-none items-center justify-center rounded-lg bg-slate-100 text-2xl">
          🎸
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="truncate text-lg font-semibold text-slate-900">
              {item.artist_name}
            </h3>
            {item.title && item.title !== item.artist_name && (
              <p className="truncate text-sm text-slate-500">{item.title}</p>
            )}
          </div>
          <FollowButton
            followed={followed}
            pending={pending}
            onToggle={() => onToggleFollow(item.artist_id, followed)}
          />
        </div>
        <p className="mt-1 text-sm text-slate-600">
          {formatDate(item.starts_at)} · {item.venue_name}
          {item.venue_city ? `, ${item.venue_city}` : ""}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-700">
            {formatDistance(item.distance_m)}
          </span>
          {price && (
            <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-700">
              {price}
            </span>
          )}
          <span
            className={`rounded-full px-2.5 py-1 font-medium ${
              STATUS_STYLES[item.status] ?? "bg-slate-100 text-slate-700"
            }`}
          >
            {item.status.replace("_", " ")}
          </span>
          <span className="rounded-full bg-indigo-50 px-2.5 py-1 font-medium text-indigo-700">
            score {item.score.toFixed(2)}
          </span>
          {item.source_url && (
            <a
              href={item.source_url}
              target="_blank"
              rel="noreferrer"
              className="ml-auto font-medium text-indigo-600 hover:underline"
            >
              Tickets ↗
            </a>
          )}
        </div>
      </div>
    </article>
  );
}
