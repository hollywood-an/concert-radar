"use client";

import { FormEvent, useEffect, useState } from "react";

import ArtistSearchBar from "@/components/ArtistSearchBar";
import FeedList from "@/components/FeedList";
import FilterDrawer, { activeFilterCount } from "@/components/FilterDrawer";
import NavBar from "@/components/NavBar";
import { useFeedSocket } from "@/hooks/useFeedSocket";
import { login } from "@/store/authSlice";
import { fetchFeedPage } from "@/store/feedSlice";
import { loadFollows } from "@/store/followsSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

function LoginCard() {
  const dispatch = useAppDispatch();
  const status = useAppSelector((state) => state.auth.status);
  const [email, setEmail] = useState("");

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void dispatch(login(email.trim()));
  };

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <h1 className="text-2xl font-bold text-slate-900">Concert Radar</h1>
        <p className="mt-1 text-sm text-slate-500">
          Live shows near you, ranked by your taste.
        </p>
        <form onSubmit={handleSubmit} className="mt-6 space-y-3">
          <input
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@example.com"
            className="w-full rounded-xl border border-slate-300 px-4 py-2.5 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200"
          />
          <button
            type="submit"
            disabled={status === "loading"}
            className="w-full rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {status === "loading" ? "Signing in…" : "Sign in"}
          </button>
          {status === "error" && (
            <p className="text-sm text-red-600">
              Login failed. Is the gateway running on localhost:8000?
            </p>
          )}
        </form>
      </div>
    </main>
  );
}

export default function FeedPage() {
  const dispatch = useAppDispatch();
  const token = useAppSelector((state) => state.auth.token);
  const filters = useAppSelector((state) => state.feed.filters);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const live = useFeedSocket(token);

  useEffect(() => {
    if (token !== null) {
      void dispatch(fetchFeedPage({ reset: true }));
      void dispatch(loadFollows());
    }
  }, [token, dispatch]);

  if (token === null) {
    return <LoginCard />;
  }

  const filterCount = activeFilterCount(filters);

  return (
    <main className="mx-auto min-h-screen max-w-2xl p-6">
      <NavBar live={live} />
      <div className="mt-6 flex items-center gap-3">
        <div className="flex-1">
          <ArtistSearchBar />
        </div>
        <button
          type="button"
          onClick={() => setDrawerOpen(true)}
          className="flex items-center gap-1.5 rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50"
        >
          Filters
          {filterCount > 0 && (
            <span className="rounded-full bg-indigo-600 px-1.5 text-xs font-semibold text-white">
              {filterCount}
            </span>
          )}
        </button>
      </div>
      <section className="mt-6">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Upcoming near you
        </h2>
        <FeedList />
      </section>
      <FilterDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </main>
  );
}
