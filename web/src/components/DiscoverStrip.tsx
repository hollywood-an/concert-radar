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
    <section className="mt-8" aria-labelledby="discover-heading">
      <h2 id="discover-heading" className="heading">
        Artists you might like
      </h2>
      <p className="mb-4 mt-1.5 text-sm text-ink-soft">
        Playing nearby, and close to the artists you already follow.
      </p>
      <ul className="-mx-4 flex snap-x scroll-px-4 gap-3 overflow-x-auto px-4 pb-3 sm:-mx-6 sm:scroll-px-6 sm:px-6">
        {discover.data.map((item) => {
          const image = item.artist_image_url ?? item.image_url;
          return (
            <li
              key={item.event_id}
              className="flex w-48 flex-none snap-start flex-col overflow-hidden rounded-[0.625rem] bg-sheet"
            >
              {image ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={image} alt="" loading="lazy" className="h-28 w-full object-cover" />
              ) : (
                <div className="flex h-28 w-full items-center justify-center bg-stub font-display text-5xl font-black text-ink/30">
                  {item.artist_name.charAt(0).toUpperCase()}
                </div>
              )}
              <div className="flex flex-1 flex-col p-3">
                <h3 className="break-words font-display text-xl font-extrabold leading-[1.05]">
                  <Link href={`/artist/${item.artist_id}`} className="hover:text-pink">
                    {item.artist_name}
                  </Link>
                </h3>
                {item.genre && (
                  <p className="mt-0.5 truncate text-xs font-semibold capitalize text-pink-deep">
                    {item.genre}
                  </p>
                )}
                <p className="mt-2 text-xs">
                  <Link href={`/event/${item.event_id}`} className="font-semibold hover:text-pink">
                    {formatDate(item.starts_at)}
                  </Link>
                </p>
                <p className="truncate text-xs text-ink-soft">
                  {item.venue_name}, {formatDistance(item.distance_m)}
                </p>
                <div className="mt-auto pt-3">
                  <ArtistFollowButton artistId={item.artist_id} />
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
