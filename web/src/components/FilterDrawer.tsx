"use client";

import { useMemo, useState } from "react";

import { fetchFeedPage, filtersChanged } from "@/store/feedSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import type { FeedFilters } from "@/types";

const EMPTY: FeedFilters = { dateRange: null, genres: [], maxDistance: null, maxPrice: null };

const MILES = 1609.34;

interface FilterDrawerProps {
  open: boolean;
  onClose: () => void;
}

export function activeFilterCount(filters: FeedFilters): number {
  return (
    (filters.dateRange !== null ? 1 : 0) +
    (filters.genres.length > 0 ? 1 : 0) +
    (filters.maxDistance !== null ? 1 : 0) +
    (filters.maxPrice !== null ? 1 : 0)
  );
}

export default function FilterDrawer({ open, onClose }: FilterDrawerProps) {
  const dispatch = useAppDispatch();
  const applied = useAppSelector((state) => state.feed.filters);
  const items = useAppSelector((state) => state.feed.items);
  const [draft, setDraft] = useState<FeedFilters>(applied);

  // Genre checkboxes come from what is currently on screen: the loaded items' headliners.
  const genreOptions = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of items) {
      for (const genre of item.artist_genres) {
        const key = genre.toLowerCase();
        counts.set(key, (counts.get(key) ?? 0) + 1);
      }
    }
    const fromItems = Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([genre]) => genre)
      .slice(0, 14);
    // Keep already-selected genres visible even when filtering hid their events.
    for (const genre of draft.genres) {
      if (!fromItems.includes(genre)) {
        fromItems.push(genre);
      }
    }
    return fromItems;
  }, [items, draft.genres]);

  const apply = (filters: FeedFilters) => {
    setDraft(filters);
    dispatch(filtersChanged(filters));
    void dispatch(fetchFeedPage({ reset: true }));
  };

  return (
    <>
      {open && (
        <button
          type="button"
          aria-label="Close filters"
          onClick={onClose}
          className="fixed inset-0 z-30 cursor-default bg-slate-900/20"
        />
      )}
      <aside
        className={`fixed right-0 top-0 z-40 h-full w-80 transform overflow-y-auto bg-white p-6 shadow-2xl transition-transform ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">Filters</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-sm font-medium text-slate-500 hover:text-slate-900"
          >
            Close
          </button>
        </div>

        <section className="mt-6">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Date range
          </h3>
          <div className="mt-2 flex items-center gap-2">
            <input
              type="date"
              value={draft.dateRange?.[0] ?? ""}
              onChange={(event) => {
                const from = event.target.value;
                const to = draft.dateRange?.[1] ?? from;
                setDraft({ ...draft, dateRange: from ? [from, to < from ? from : to] : null });
              }}
              className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            />
            <span className="text-slate-400">–</span>
            <input
              type="date"
              value={draft.dateRange?.[1] ?? ""}
              onChange={(event) => {
                const to = event.target.value;
                const from = draft.dateRange?.[0] ?? to;
                setDraft({ ...draft, dateRange: to ? [from > to ? to : from, to] : null });
              }}
              className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            />
          </div>
        </section>

        <section className="mt-6">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Genres
          </h3>
          <div className="mt-2 grid grid-cols-2 gap-1.5">
            {genreOptions.length === 0 && (
              <p className="col-span-2 text-sm text-slate-400">No genres loaded yet.</p>
            )}
            {genreOptions.map((genre) => (
              <label key={genre} className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={draft.genres.includes(genre)}
                  onChange={(event) =>
                    setDraft({
                      ...draft,
                      genres: event.target.checked
                        ? [...draft.genres, genre]
                        : draft.genres.filter((g) => g !== genre),
                    })
                  }
                  className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                />
                <span className="truncate">{genre}</span>
              </label>
            ))}
          </div>
        </section>

        <section className="mt-6">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Max distance{" "}
            {draft.maxDistance !== null && (
              <span className="normal-case text-slate-700">
                — {(draft.maxDistance / MILES).toFixed(0)} mi
              </span>
            )}
          </h3>
          <input
            type="range"
            min={1}
            max={50}
            value={draft.maxDistance !== null ? Math.round(draft.maxDistance / MILES) : 50}
            onChange={(event) => {
              const miles = Number(event.target.value);
              setDraft({ ...draft, maxDistance: miles >= 50 ? null : miles * MILES });
            }}
            className="mt-2 w-full accent-indigo-600"
          />
        </section>

        <section className="mt-6">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Max price{" "}
            {draft.maxPrice !== null && (
              <span className="normal-case text-slate-700">
                — ${(draft.maxPrice / 100).toFixed(0)}
              </span>
            )}
          </h3>
          <input
            type="range"
            min={10}
            max={200}
            step={5}
            value={draft.maxPrice !== null ? draft.maxPrice / 100 : 200}
            onChange={(event) => {
              const dollars = Number(event.target.value);
              setDraft({ ...draft, maxPrice: dollars >= 200 ? null : dollars * 100 });
            }}
            className="mt-2 w-full accent-indigo-600"
          />
        </section>

        <div className="mt-8 flex gap-2">
          <button
            type="button"
            onClick={() => apply(draft)}
            className="flex-1 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500"
          >
            Apply
          </button>
          <button
            type="button"
            onClick={() => apply(EMPTY)}
            className="rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Clear
          </button>
        </div>
      </aside>
    </>
  );
}
