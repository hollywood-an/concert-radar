"use client";

import Link from "next/link";
import { useEffect, useMemo } from "react";

import ArtistFollowButton from "@/components/ArtistFollowButton";
import DateStub from "@/components/DateStub";
import NavBar from "@/components/NavBar";
import { PageNotice, SignInNotice } from "@/components/PageNotice";
import { useResource } from "@/hooks/useResource";
import { getArtist } from "@/lib/api";
import { dateParts, formatDistance, formatPrice } from "@/lib/format";
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
      className={`${size} flex flex-none items-center justify-center rounded-full bg-stub font-display font-black text-ink`}
    >
      {artist.name.charAt(0).toUpperCase()}
    </div>
  );
}

interface ShowRowProps {
  show: UpcomingShow;
  artistName: string;
  following: boolean;
}

function ShowRow({ show, artistName, following }: ShowRowProps) {
  const price = formatPrice(show.price_min_cents, show.price_max_cents);
  const { time } = dateParts(show.starts_at);
  return (
    <li className="ticket-shadow">
      <Link
        href={`/event/${show.event_id}`}
        className={`ticket group ${show.dismissed ? "opacity-60" : ""}`}
      >
        <DateStub iso={show.starts_at} tone={following ? "following" : "plain"} />
        <div className="min-w-0 flex-1 p-4">
          <p className="font-display text-xl font-extrabold leading-tight group-hover:text-pink">
            {show.venue_name}
          </p>
          <p className="mt-0.5 text-sm">
            <span className="font-semibold">{time}</span>
            {show.venue_city && <span className="text-ink-soft"> in {show.venue_city}</span>}
          </p>
          {show.title && show.title !== artistName && (
            <p className="mt-0.5 truncate text-sm text-ink-soft">{show.title}</p>
          )}
          <div className="mt-2 flex flex-wrap gap-2">
            {show.distance_m !== null && (
              <span className="chip">{formatDistance(show.distance_m)}</span>
            )}
            {price && <span className="chip">{price}</span>}
            {show.dismissed && <span className="chip">Hidden from your feed</span>}
          </div>
        </div>
      </Link>
    </li>
  );
}

function SimilarArtistRow({ artist }: { artist: ArtistSummary }) {
  return (
    <li className="flex items-center gap-3 py-3">
      <ArtistImage artist={artist} size="h-11 w-11 text-xl" />
      <div className="min-w-0 flex-1">
        <Link
          href={`/artist/${artist.id}`}
          className="block break-words font-display text-xl font-extrabold leading-tight hover:text-pink"
        >
          {artist.name}
        </Link>
        {artist.genres.length > 0 && (
          <p className="truncate text-xs text-ink-soft">{artist.genres.slice(0, 4).join(", ")}</p>
        )}
      </div>
      <ArtistFollowButton artistId={artist.id} />
    </li>
  );
}

export default function ArtistPage({ params }: { params: { id: string } }) {
  const dispatch = useAppDispatch();
  const token = useAppSelector((state) => state.auth.token);
  const following = useAppSelector((state) => state.follows.artistIds.includes(params.id));
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
    return <PageNotice>Loading the artist…</PageNotice>;
  }
  if (artist.status === "not_found") {
    return (
      <PageNotice>
        There is no artist at this address.{" "}
        <Link href="/" className="link">
          Back to your feed
        </Link>
      </PageNotice>
    );
  }
  if (artist.status === "error") {
    return <PageNotice>This artist didn&apos;t load. Reload the page to try again.</PageNotice>;
  }

  const { data } = artist;

  return (
    <main className="mx-auto min-h-screen max-w-4xl px-4 py-6 sm:px-6">
      <NavBar />
      <header className="mt-10 flex flex-wrap items-center gap-x-6 gap-y-4">
        <ArtistImage artist={data} size="h-24 w-24 text-5xl" />
        <div className="min-w-0 flex-1 basis-64">
          <h1 className="break-words font-display text-5xl font-black leading-[0.95] sm:text-6xl">
            {data.name}
          </h1>
          {data.genres.length > 0 && (
            <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Genres">
              {data.genres.map((genre) => (
                <li key={genre} className="chip !bg-sheet capitalize">
                  {genre}
                </li>
              ))}
            </ul>
          )}
        </div>
        <ArtistFollowButton artistId={data.id} />
      </header>

      <div className="mt-10 grid gap-10 md:grid-cols-2">
        <section aria-labelledby="shows-heading" className="min-w-0">
          <h2 id="shows-heading" className="heading">
            Upcoming shows
          </h2>
          {data.upcoming.length === 0 ? (
            <p className="mt-3 text-sm text-ink-soft">
              {following
                ? "No dates listed. You follow this artist, so new ones will appear in your feed when they are announced."
                : "No dates listed. Follow this artist to see new ones in your feed when they are announced."}
            </p>
          ) : (
            <ul className="mt-4 space-y-3">
              {data.upcoming.map((show) => (
                <ShowRow
                  key={show.event_id}
                  show={show}
                  artistName={data.name}
                  following={following}
                />
              ))}
            </ul>
          )}
        </section>
        <section aria-labelledby="similar-heading" className="min-w-0">
          <h2 id="similar-heading" className="heading">
            Similar artists
          </h2>
          {data.similar.length === 0 ? (
            <p className="mt-3 text-sm text-ink-soft">
              Nothing close yet. Matches appear once this artist&apos;s genres are known.
            </p>
          ) : (
            <ul className="mt-2 divide-y divide-line border-y border-line">
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
