"use client";

import { useEffect, useState } from "react";

import EventMap from "@/components/EventMap";
import FilterDrawer, { activeFilterCount } from "@/components/FilterDrawer";
import NavBar from "@/components/NavBar";
import { fetchEntireFeed } from "@/store/feedSlice";
import { loadFollows } from "@/store/followsSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

export default function MapPage() {
  const dispatch = useAppDispatch();
  const token = useAppSelector((state) => state.auth.token);
  const status = useAppSelector((state) => state.auth.status);
  const { items, filters } = useAppSelector((state) => state.feed);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    if (token !== null) {
      void dispatch(fetchEntireFeed());
      void dispatch(loadFollows());
    }
  }, [token, dispatch, filters]);

  if (token === null) {
    return (
      <main className="mx-auto min-h-screen max-w-4xl p-6">
        <NavBar />
        <p className="mt-10 text-center text-sm text-slate-500">
          {status === "idle" ? "Sign in on the Feed page to see the map." : "Loading…"}
        </p>
      </main>
    );
  }

  const filterCount = activeFilterCount(filters);

  return (
    <main className="mx-auto min-h-screen max-w-4xl p-6">
      <NavBar />
      <div className="mt-6 flex items-center justify-between">
        <p className="text-sm text-slate-500">
          {items.length} upcoming {items.length === 1 ? "show" : "shows"} in your radius
        </p>
        <button
          type="button"
          onClick={() => setDrawerOpen(true)}
          className="flex items-center gap-1.5 rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50"
        >
          Filters
          {filterCount > 0 && (
            <span className="rounded-full bg-indigo-600 px-1.5 text-xs font-semibold text-white">
              {filterCount}
            </span>
          )}
        </button>
      </div>
      <div className="mt-4">
        <EventMap items={items} />
      </div>
      <FilterDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </main>
  );
}
