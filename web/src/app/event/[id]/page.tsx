"use client";

import Link from "next/link";
import { useEffect, useMemo } from "react";

import ArtistFollowButton from "@/components/ArtistFollowButton";
import DateStub from "@/components/DateStub";
import NavBar from "@/components/NavBar";
import { PageNotice, SignInNotice } from "@/components/PageNotice";
import StatusBadge from "@/components/StatusBadge";
import VenueMap from "@/components/VenueMap";
import { useRecordActivity } from "@/hooks/useRecordActivity";
import { useResource } from "@/hooks/useResource";
import { getEvent } from "@/lib/api";
import { dateParts, formatPrice } from "@/lib/format";
import { loadFollows } from "@/store/followsSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import type { EventArtist } from "@/types";

function LineupEntry({ artist }: { artist: EventArtist }) {
  return (
    <li className="flex items-center justify-between gap-3 py-3.5">
      <div className="min-w-0">
        <Link
          href={`/artist/${artist.id}`}
          className="block break-words font-display text-xl font-extrabold leading-tight hover:text-pink"
        >
          {artist.name}
        </Link>
        <p className="truncate text-xs text-ink-soft">
          {artist.billing === 0 ? "Headliner" : "Support"}
          {artist.genres.length > 0 && `: ${artist.genres.slice(0, 4).join(", ")}`}
        </p>
      </div>
      <ArtistFollowButton artistId={artist.id} />
    </li>
  );
}

export default function EventPage({ params }: { params: { id: string } }) {
  const dispatch = useAppDispatch();
  const token = useAppSelector((state) => state.auth.token);
  const followedIds = useAppSelector((state) => state.follows.artistIds);
  const load = useMemo(
    () => (token === null ? null : () => getEvent(params.id)),
    [token, params.id],
  );
  const event = useResource(load);
  const record = useRecordActivity();

  // Once per show page that actually loaded, not per render or per failed address.
  const loadedId = event.status === "loaded" ? event.data.id : null;
  useEffect(() => {
    if (loadedId !== null) {
      record("show_opened", loadedId);
    }
  }, [loadedId, record]);

  useEffect(() => {
    if (token !== null) {
      void dispatch(loadFollows());
    }
  }, [token, dispatch]);

  if (token === null) {
    return <SignInNotice purpose="see this show" />;
  }
  if (event.status === "loading") {
    return <PageNotice>Loading the show…</PageNotice>;
  }
  if (event.status === "not_found") {
    return (
      <PageNotice>
        There is no show at this address. It may have been removed.{" "}
        <Link href="/" className="link">
          Back to your feed
        </Link>
      </PageNotice>
    );
  }
  if (event.status === "error") {
    return <PageNotice>This show didn&apos;t load. Reload the page to try again.</PageNotice>;
  }

  const { data } = event;
  const price = formatPrice(data.price_min_cents, data.price_max_cents);
  const title = data.title ?? data.artists[0]?.name ?? "Untitled show";
  const { time } = dateParts(data.starts_at);
  const place = [data.venue.city, data.venue.state].filter(Boolean).join(", ");
  const following = data.artists.some((artist) => followedIds.includes(artist.id));

  return (
    <main className="mx-auto min-h-screen max-w-4xl px-4 py-6 sm:px-6">
      <NavBar />
      <div className="ticket-shadow mt-8">
        <header className="ticket ticket-lg">
          <DateStub iso={data.starts_at} tone={following ? "following" : "plain"} large />
          <div className="flex min-w-0 flex-1 flex-col gap-5 p-5 sm:flex-row sm:items-center sm:p-7">
            <div className="min-w-0 flex-1">
              <h1 className="break-words font-display text-4xl font-black leading-[0.95] sm:text-5xl">
                {title}
              </h1>
              <p className="mt-3 text-lg">
                <span className="font-semibold">{time}</span>{" "}
                <span className="text-ink-soft">
                  at {data.venue.name}
                  {place && `, ${place}`}
                </span>
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <StatusBadge status={data.status} />
                {price && <span className="chip">{price}</span>}
              </div>
              {data.source_url && (
                <a
                  href={data.source_url}
                  target="_blank"
                  rel="noreferrer"
                  onClick={() => record("ticket_click", data.id)}
                  className="button-primary mt-5"
                >
                  Get tickets<span className="sr-only"> (opens in a new tab)</span>
                </a>
              )}
            </div>
            {data.image_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={data.image_url}
                alt=""
                className="h-36 w-full flex-none rounded-md object-cover sm:h-40 sm:w-56"
              />
            )}
          </div>
        </header>
      </div>

      <div className="mt-10 grid gap-10 md:grid-cols-2">
        <section aria-labelledby="lineup-heading" className="min-w-0">
          <h2 id="lineup-heading" className="heading">
            Lineup
          </h2>
          {data.artists.length === 0 ? (
            <p className="mt-3 text-sm text-ink-soft">The lineup hasn&apos;t been announced.</p>
          ) : (
            <ul className="mt-2 divide-y divide-line border-y border-line">
              {data.artists.map((artist) => (
                <LineupEntry key={artist.id} artist={artist} />
              ))}
            </ul>
          )}
        </section>
        <section aria-labelledby="venue-heading" className="min-w-0">
          <h2 id="venue-heading" className="heading">
            {data.venue.name}
          </h2>
          {place && <p className="mb-4 mt-1.5 text-sm text-ink-soft">{place}</p>}
          <VenueMap location={data.venue.location} />
        </section>
      </div>
    </main>
  );
}
