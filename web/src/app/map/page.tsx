"use client";

import { useEffect, useState } from "react";

import EventMap from "@/components/EventMap";
import FilterDrawer, { activeFilterCount } from "@/components/FilterDrawer";
import NavBar from "@/components/NavBar";
import { SignInNotice } from "@/components/PageNotice";
import { fetchEntireFeed } from "@/store/feedSlice";
import { loadFollows } from "@/store/followsSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

export default function MapPage() {
  const dispatch = useAppDispatch();
  const token = useAppSelector((state) => state.auth.token);
  const { items, filters } = useAppSelector((state) => state.feed);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    if (token !== null) {
      void dispatch(fetchEntireFeed());
      void dispatch(loadFollows());
    }
  }, [token, dispatch, filters]);

  if (token === null) {
    return <SignInNotice purpose="see the map" />;
  }

  const filterCount = activeFilterCount(filters);

  return (
    <main className="mx-auto min-h-screen max-w-5xl px-4 py-6 sm:px-6">
      <NavBar />
      <div className="mt-8 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="heading !text-5xl">Shows on the map</h1>
          <p className="mt-2 text-sm text-ink-soft" role="status">
            {items.length === 0
              ? "No shows within your travel distance."
              : `${items.length} upcoming ${
                  items.length === 1 ? "show" : "shows"
                } within your travel distance. Click a circle to zoom in, or a dot for the show.`}
          </p>
        </div>
        <button type="button" onClick={() => setDrawerOpen(true)} className="button-quiet">
          Filters
          {filterCount > 0 && (
            <span className="ml-1.5 rounded-full bg-pink px-1.5 text-xs font-semibold text-white">
              {filterCount}
            </span>
          )}
        </button>
      </div>
      <div className="mt-5">
        <EventMap items={items} />
      </div>
      <FilterDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </main>
  );
}
