"use client";

import Link from "next/link";
import { useEffect, useMemo } from "react";

import ArtistFollowButton from "@/components/ArtistFollowButton";
import NavBar from "@/components/NavBar";
import { PageNotice, SignInNotice } from "@/components/PageNotice";
import { useResource } from "@/hooks/useResource";
import { getArtist } from "@/lib/api";
import { formatDate, formatDistance, formatPrice } from "@/lib/format";
import { loadFollows } from "@/store/followsSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import type { ArtistSummary, UpcomingShow } from "@/types";

function ArtistImage({ artist, size }: { artist: ArtistSummary; size: string }) {
  if (artist.image_url) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={artist.image_url}
        alt=""
        className={`${size} flex-none rounded-full object-cover`}
      />
    );
  }
  return (
    <div
      className={`${size} flex flex-none items-center justify-center rounded-full bg-indigo-100 font-bold text-indigo-700`}
    >
      {artist.name.charAt(0).toUpperCase()}
    </div>
  );
}

function ShowRow({ show }: { show: UpcomingShow }) {
  const price = formatPrice(show.price_min_cents, show.price_max_cents);
  return (
    <li>
      <Link
        href={`/event/${show.event_id}`}
        className={`block rounded-xl border border-slate-200 bg-white p-4 shadow-sm hover:border-indigo-300 ${
          show.dismissed ? "opacity-60" : ""
        }`}
      >
        <p className="font-semibold text-slate-900">{formatDate(show.starts_at)}</p>
        {show.title && <p className="truncate text-sm text-slate-600">{show.title}</p>}
        <p className="text-sm text-slate-500">
          {show.venue_name}
          {show.venue_city ? `, ${show.venue_city}` : ""}
        </p>
        <div className="mt-2 flex flex-wrap gap-2 text-xs">
          {show.distance_m !== null && (
            <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-700">
              {formatDistance(show.distance_m)}
            </span>
          )}
          {price && (
            <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-700">
              {price}
            </span>
          )}
          {show.dismissed && (
            <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-500">
              dismissed
            </span>
          )}
        </div>
      </Link>
    </li>
  );
}

function SimilarArtistRow({ artist }: { artist: ArtistSummary }) {
  return (
    <li className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
      <ArtistImage artist={artist} size="h-10 w-10" />
      <div className="min-w-0 flex-1">
        <Link
          href={`/artist/${artist.id}`}
          className="block truncate font-semibold text-slate-900 hover:text-indigo-600"
        >
          {artist.name}
        </Link>
        {artist.genres.length > 0 && (
          <p className="truncate text-xs text-slate-500">{artist.genres.join(" · ")}</p>
        )}
      </div>
      <ArtistFollowButton artistId={artist.id} />
    </li>
  );
}

export default function ArtistPage({ params }: { params: { id: string } }) {
  const dispatch = useAppDispatch();
  const token = useAppSelector((state) => state.auth.token);
  const load = useMemo(
    () => (token === null ? null : () => getArtist(token, params.id)),
    [token, params.id],
  );
  const artist = useResource(load);

  useEffect(() => {
    if (token !== null) {
      void dispatch(loadFollows());
    }
  }, [token, dispatch]);

  if (token === null) {
    return <SignInNotice purpose="see this artist" />;
  }
  if (artist.status === "loading") {
    return <PageNotice>Loading artist…</PageNotice>;
  }
  if (artist.status === "not_found") {
    return (
      <PageNotice>
        This artist doesn&apos;t exist.{" "}
        <Link href="/" className="font-medium text-indigo-600 hover:underline">
          Back to your feed
        </Link>
      </PageNotice>
    );
  }
  if (artist.status === "error") {
    return (
      <PageNotice>Couldn&apos;t load this artist. Try reloading the page.</PageNotice>
    );
  }

  const { data } = artist;

  return (
    <main className="mx-auto min-h-screen max-w-4xl p-6">
      <NavBar />
      <header className="mt-8 flex items-center gap-5">
        <ArtistImage artist={data} size="h-24 w-24 text-3xl" />
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-2xl font-bold text-slate-900">{data.name}</h2>
          {data.genres.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {data.genres.map((genre) => (
                <span
                  key={genre}
                  className="rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700"
                >
                  {genre}
                </span>
              ))}
            </div>
          )}
        </div>
        <ArtistFollowButton artistId={data.id} />
      </header>

      <div className="mt-8 grid gap-8 md:grid-cols-2">
        <section>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Upcoming shows
          </h3>
          {data.upcoming.length === 0 ? (
            <p className="mt-3 text-sm text-slate-500">No upcoming shows.</p>
          ) : (
            <ul className="mt-3 space-y-3">
              {data.upcoming.map((show) => (
                <ShowRow key={show.event_id} show={show} />
              ))}
            </ul>
          )}
        </section>
        <section>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Similar artists
          </h3>
          <p className="mt-1 text-xs text-slate-400">Closest by genre</p>
          {data.similar.length === 0 ? (
            <p className="mt-3 text-sm text-slate-500">No similar artists yet.</p>
          ) : (
            <ul className="mt-3 space-y-2">
              {data.similar.map((similar) => (
                <SimilarArtistRow key={similar.id} artist={similar} />
              ))}
            </ul>
          )}
        </section>
      </div>
    </main>
  );
}
