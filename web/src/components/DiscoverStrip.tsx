"use client";

import Link from "next/link";
import { useMemo } from "react";

import ArtistFollowButton from "@/components/ArtistFollowButton";
import { useResource } from "@/hooks/useResource";
import { getDiscover } from "@/lib/api";
import { formatDate, formatDistance } from "@/lib/format";
import { useAppSelector } from "@/store/hooks";

// Nearby shows by artists the user doesn't follow yet, from the recommender service.
// Renders nothing while loading, when there is nothing to suggest, or when the
// recommender is unavailable, so the feed below never waits on it.
export default function DiscoverStrip() {
  const token = useAppSelector((state) => state.auth.token);
  const load = useMemo(() => (token === null ? null : () => getDiscover(token)), [token]);
  const discover = useResource(load);

  if (discover.status !== "loaded" || discover.data.length === 0) {
    return null;
  }

  return (
    <section className="mt-6">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Discover</h2>
      <p className="mb-3 text-sm text-slate-500">
        Artists you don&apos;t follow yet, picked from your taste.
      </p>
      <div className="-mx-1 flex gap-3 overflow-x-auto px-1 pb-2">
        {discover.data.map((item) => {
          const image = item.artist_image_url ?? item.image_url;
          return (
            <article
              key={item.event_id}
              className="flex w-52 flex-none flex-col rounded-xl border border-slate-200 bg-white p-3 shadow-sm"
            >
              {image ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={image} alt="" className="h-28 w-full rounded-lg object-cover" />
              ) : (
                <div className="flex h-28 w-full items-center justify-center rounded-lg bg-slate-100 text-2xl">
                  🎸
                </div>
              )}
              <h3 className="mt-2 truncate font-semibold text-slate-900">
                <Link href={`/artist/${item.artist_id}`} className="hover:text-indigo-600">
                  {item.artist_name}
                </Link>
              </h3>
              {item.genre && (
                <p className="truncate text-xs font-medium capitalize text-indigo-600">
                  {item.genre}
                </p>
              )}
              <p className="mt-1 text-xs text-slate-600">
                <Link href={`/event/${item.event_id}`} className="hover:text-indigo-600">
                  {formatDate(item.starts_at)}
                </Link>
              </p>
              <p className="truncate text-xs text-slate-500">
                {item.venue_name} · {formatDistance(item.distance_m)}
              </p>
              <div className="mt-auto pt-2">
                <ArtistFollowButton artistId={item.artist_id} />
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
