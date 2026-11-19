"use client";

import Link from "next/link";

import ArtistFollowButton from "@/components/ArtistFollowButton";
import DateStub from "@/components/DateStub";
import StatusBadge from "@/components/StatusBadge";
import { dateParts, formatDistance, formatMatch, formatPrice } from "@/lib/format";
import { dismissEvent } from "@/store/feedSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import type { FeedItem } from "@/types";

interface EventCardProps {
  item: FeedItem;
  fresh?: boolean;
}

export default function EventCard({ item, fresh = false }: EventCardProps) {
  const dispatch = useAppDispatch();
  const followCount = useAppSelector((state) => state.follows.artistIds.length);
  const following = useAppSelector((state) => state.follows.artistIds.includes(item.artist_id));
  const price = formatPrice(item.price_min_cents, item.price_max_cents);
  const match = formatMatch(item.score, followCount);
  const { time } = dateParts(item.starts_at);
  const eventHref = `/event/${item.event_id}`;

  return (
    <div className="ticket-shadow">
      <article className="ticket">
        <Link
          href={eventHref}
          aria-label={`Details for ${item.artist_name} at ${item.venue_name}`}
          className="flex"
        >
          <DateStub
            iso={item.starts_at}
            tone={fresh ? "fresh" : following ? "following" : "plain"}
          />
        </Link>
        <div className="flex min-w-0 flex-1 gap-4 p-4">
          {item.image_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={item.image_url}
              alt=""
              loading="lazy"
              className="hidden h-20 w-20 flex-none rounded-md object-cover sm:block"
            />
          )}
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                {fresh && <p className="text-xs font-semibold text-pink">New match</p>}
                <h3 className="break-words font-display text-2xl font-extrabold leading-[1.05]">
                  <Link href={`/artist/${item.artist_id}`} className="hover:text-pink">
                    {item.artist_name}
                  </Link>
                </h3>
                {item.title && item.title !== item.artist_name && (
                  <p className="mt-0.5 truncate text-sm text-ink-soft">{item.title}</p>
                )}
              </div>
              <div className="flex flex-none items-center gap-1">
                <ArtistFollowButton artistId={item.artist_id} />
                <button
                  type="button"
                  aria-label={`Hide ${item.artist_name} at ${item.venue_name}`}
                  title="Not interested"
                  onClick={() => void dispatch(dismissEvent(item.event_id))}
                  className="rounded-full p-2 text-ink-faint hover:bg-paper hover:text-ink"
                >
                  <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4" aria-hidden="true">
                    <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
                  </svg>
                </button>
              </div>
            </div>
            <p className="mt-1.5 text-sm">
              <Link href={eventHref} className="font-semibold hover:text-pink">
                {time}
              </Link>{" "}
              <span className="text-ink-soft">
                at {item.venue_name}
                {item.venue_city ? `, ${item.venue_city}` : ""}
              </span>
            </p>
            <div className="mt-2.5 flex flex-wrap items-center gap-2">
              <span className="chip">{formatDistance(item.distance_m)}</span>
              {price && <span className="chip">{price}</span>}
              <StatusBadge status={item.status} />
              {match && <span className="chip !bg-pink-wash !text-pink-deep">{match}</span>}
              {item.source_url && (
                <a
                  href={item.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="link ml-auto text-sm"
                >
                  Get tickets<span className="sr-only"> (opens in a new tab)</span>
                </a>
              )}
            </div>
          </div>
        </div>
      </article>
    </div>
  );
}
