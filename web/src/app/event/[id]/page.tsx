"use client";

import Link from "next/link";
import { useEffect, useMemo } from "react";

import ArtistFollowButton from "@/components/ArtistFollowButton";
import NavBar from "@/components/NavBar";
import { PageNotice, SignInNotice } from "@/components/PageNotice";
import StatusBadge from "@/components/StatusBadge";
import VenueMap from "@/components/VenueMap";
import { useResource } from "@/hooks/useResource";
import { getEvent } from "@/lib/api";
import { formatLongDate, formatPrice } from "@/lib/format";
import { loadFollows } from "@/store/followsSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import type { EventArtist } from "@/types";

function LineupEntry({ artist }: { artist: EventArtist }) {
  return (
    <li className="flex items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <Link
          href={`/artist/${artist.id}`}
          className="block truncate font-semibold text-slate-900 hover:text-indigo-600"
        >
          {artist.name}
        </Link>
        <p className="truncate text-xs text-slate-500">
          {artist.billing === 0 ? "Headliner" : "Support"}
          {artist.genres.length > 0 && ` · ${artist.genres.join(", ")}`}
        </p>
      </div>
      <ArtistFollowButton artistId={artist.id} />
    </li>
  );
}

export default function EventPage({ params }: { params: { id: string } }) {
  const dispatch = useAppDispatch();
  const token = useAppSelector((state) => state.auth.token);
  const load = useMemo(
    () => (token === null ? null : () => getEvent(params.id)),
    [token, params.id],
  );
  const event = useResource(load);

  useEffect(() => {
    if (token !== null) {
      void dispatch(loadFollows());
    }
  }, [token, dispatch]);

  if (token === null) {
    return <SignInNotice purpose="see this event" />;
  }
  if (event.status === "loading") {
    return <PageNotice>Loading event…</PageNotice>;
  }
  if (event.status === "not_found") {
    return (
      <PageNotice>
        This event doesn&apos;t exist.{" "}
        <Link href="/" className="font-medium text-indigo-600 hover:underline">
          Back to your feed
        </Link>
      </PageNotice>
    );
  }
  if (event.status === "error") {
    return (
      <PageNotice>Couldn&apos;t load this event. Try reloading the page.</PageNotice>
    );
  }

  const { data } = event;
  const price = formatPrice(data.price_min_cents, data.price_max_cents);
  const title = data.title ?? data.artists[0]?.name ?? "Untitled show";

  return (
    <main className="mx-auto min-h-screen max-w-4xl p-6">
      <NavBar />
      <header className="mt-8 flex gap-5">
        {data.image_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={data.image_url}
            alt=""
            className="h-28 w-28 flex-none rounded-xl object-cover"
          />
        )}
        <div className="min-w-0">
          <h2 className="text-2xl font-bold text-slate-900">{title}</h2>
          <p className="mt-1 text-slate-600">{formatLongDate(data.starts_at)}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <StatusBadge status={data.status} />
            {price && (
              <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-700">
                {price}
              </span>
            )}
          </div>
          {data.source_url && (
            <a
              href={data.source_url}
              target="_blank"
              rel="noreferrer"
              className="mt-4 inline-block rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500"
            >
              Get tickets ↗
            </a>
          )}
        </div>
      </header>

      <div className="mt-8 grid gap-6 md:grid-cols-2">
        <section>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Venue
          </h3>
          <p className="mt-2 font-semibold text-slate-900">{data.venue.name}</p>
          <p className="mb-3 text-sm text-slate-600">
            {[data.venue.city, data.venue.state].filter(Boolean).join(", ")}
          </p>
          <VenueMap location={data.venue.location} />
        </section>
        <section>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Lineup
          </h3>
          {data.artists.length === 0 ? (
            <p className="mt-2 text-sm text-slate-500">No lineup announced yet.</p>
          ) : (
            <ul className="mt-2 divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white px-4">
              {data.artists.map((artist) => (
                <LineupEntry key={artist.id} artist={artist} />
              ))}
            </ul>
          )}
        </section>
      </div>
    </main>
  );
}
