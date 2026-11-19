"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { useSessionReady } from "@/app/providers";
import ArtistSearchBar from "@/components/ArtistSearchBar";
import DiscoverStrip from "@/components/DiscoverStrip";
import FeedList from "@/components/FeedList";
import FilterDrawer, { activeFilterCount } from "@/components/FilterDrawer";
import NavBar from "@/components/NavBar";
import RadarHero from "@/components/RadarHero";
import RadarMark from "@/components/RadarMark";
import { useFeedSocket } from "@/hooks/useFeedSocket";
import { login } from "@/store/authSlice";
import { fetchFeedPage } from "@/store/feedSlice";
import { loadFollows } from "@/store/followsSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

const MILES = 1609.34;

function SignIn() {
  const dispatch = useAppDispatch();
  const status = useAppSelector((state) => state.auth.status);
  const [email, setEmail] = useState("");

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void dispatch(login(email.trim()));
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col px-6 py-8">
      <p className="flex items-center gap-2 font-display text-[1.75rem] font-black uppercase leading-none">
        <RadarMark className="h-7 w-7" />
        Concert Radar
      </p>
      <div className="grid flex-1 items-center gap-10 py-10 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
        <div>
          <h1 className="font-display text-[clamp(3rem,9vw,6rem)] font-black uppercase leading-none">
            Every show near you, ranked by who you follow.
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-relaxed text-ink-soft">
            Follow the artists you like and set how far you&apos;ll travel. The feed sorts every
            upcoming show nearby by how well it fits your taste, and tells you when someone
            you follow announces a date.
          </p>
          <form onSubmit={handleSubmit} className="mt-8 flex max-w-xl flex-col gap-3 sm:flex-row">
            <label htmlFor="email" className="sr-only">
              Email address
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
              className="field !rounded-full !px-5 !py-3 !text-base"
            />
            <button
              type="submit"
              disabled={status === "loading"}
              className="button-primary flex-none !px-7 !py-3 !text-base"
            >
              {status === "loading" ? "Signing in…" : "Sign in"}
            </button>
          </form>
          {status === "error" && (
            <p role="alert" className="mt-3 text-sm font-medium text-red-800">
              Sign-in didn&apos;t go through. The server may be offline; try again in a minute.
            </p>
          )}
          <p className="mt-4 max-w-xl text-sm text-ink-soft">
            This is a demo, so any email address works. There is no password, and nothing is
            ever sent to the address.
          </p>
        </div>
        <RadarHero />
      </div>
      <footer className="border-t border-line pt-4 text-sm text-ink-soft">
        Shows come from Ticketmaster for the Columbus, Ohio area.{" "}
        <a href="https://github.com/hollywood-an/concert-radar" className="link">
          How it works, on GitHub
        </a>
      </footer>
    </main>
  );
}

// Shown until the user follows someone: without follows the feed is only a calendar.
function GetStarted() {
  const radiusMeters = useAppSelector((state) => state.auth.user?.travel_radius_m ?? null);
  const miles = radiusMeters === null ? null : Math.round(radiusMeters / MILES);
  return (
    <aside className="mt-6 rounded-[0.625rem] bg-highlighter p-5">
      <p className="font-display text-2xl font-extrabold leading-tight">
        Follow a few artists to rank this list
      </p>
      <p className="mt-1.5 max-w-prose text-sm">
        Right now it is every show
        {miles === null ? " near" : ` within ${miles} miles of`} your home location, soonest
        first. Search for an artist above or press Follow on any show, and the list re-sorts
        around your taste.{" "}
        <Link href="/settings" className="font-semibold underline underline-offset-4">
          Change your location or distance
        </Link>
      </p>
    </aside>
  );
}

export default function FeedPage() {
  const dispatch = useAppDispatch();
  const token = useAppSelector((state) => state.auth.token);
  const filters = useAppSelector((state) => state.feed.filters);
  const followCount = useAppSelector((state) => state.follows.artistIds.length);
  const followsLoaded = useAppSelector((state) => state.follows.loaded);
  const hasShows = useAppSelector((state) => state.feed.items.length > 0);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const live = useFeedSocket(token);
  const sessionReady = useSessionReady();

  useEffect(() => {
    if (token !== null) {
      void dispatch(fetchFeedPage({ reset: true }));
      void dispatch(loadFollows());
    }
  }, [token, dispatch]);

  if (token === null) {
    // Until the stored session has been checked, show neither the form nor the feed.
    return sessionReady ? <SignIn /> : <main className="min-h-screen" aria-busy="true" />;
  }

  const filterCount = activeFilterCount(filters);

  return (
    <main className="mx-auto min-h-screen max-w-3xl px-4 py-6 sm:px-6">
      <NavBar live={live} />
      <div className="mt-6 flex items-center gap-3">
        <div className="flex-1">
          <ArtistSearchBar />
        </div>
        <button type="button" onClick={() => setDrawerOpen(true)} className="button-quiet !py-2.5">
          Filters
          {filterCount > 0 && (
            <span className="ml-1.5 rounded-full bg-pink px-1.5 text-xs font-semibold text-white">
              {filterCount}
            </span>
          )}
        </button>
      </div>
      {followsLoaded && followCount === 0 && hasShows && <GetStarted />}
      <DiscoverStrip />
      <section className="mt-8">
        <h1 className="heading mb-4">Upcoming near you</h1>
        <FeedList />
      </section>
      <FilterDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </main>
  );
}
