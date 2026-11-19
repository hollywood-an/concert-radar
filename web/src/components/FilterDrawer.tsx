"use client";

import { useEffect, useMemo, useRef, useState } from "react";

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
  const radiusMeters = useAppSelector((state) => state.auth.user?.travel_radius_m ?? null);
  const [draft, setDraft] = useState<FeedFilters>(applied);

  // The distance slider runs up to the travel radius from Settings; its far end means
  // "no extra limit". The price filter is offered only when some loaded show lists a
  // price, because the API drops unpriced shows whenever a maximum is set.
  const maxMiles = Math.max(2, Math.round((radiusMeters ?? 50 * MILES) / MILES));
  const anyPriced = items.some((item) => item.price_min_cents !== null);

  // Off-screen is not enough: without inert, Tab would walk through the hidden form.
  // Set on the element directly because React 18 does not pass the attribute through.
  const asideRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    asideRef.current?.toggleAttribute("inert", !open);
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

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
          className="fixed inset-0 z-30 cursor-default bg-ink/30"
        />
      )}
      {/* Shadow only while open: off-screen, it would bleed onto the page's right edge. */}
      <aside
        ref={asideRef}
        aria-label="Filters"
        className={`fixed right-0 top-0 z-40 h-full w-80 max-w-full transform overflow-y-auto bg-sheet p-6 transition-transform ${
          open ? "translate-x-0 shadow-2xl" : "translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between">
          <h2 className="heading">Filters</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-sm font-semibold text-ink underline-offset-4 hover:text-pink hover:underline"
          >
            Close
          </button>
        </div>

        <section className="mt-6">
          <h3 className="text-sm font-semibold text-ink">
            Dates
          </h3>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <label className="text-xs text-ink-soft">
              From
              <input
                type="date"
                value={draft.dateRange?.[0] ?? ""}
                onChange={(event) => {
                  const from = event.target.value;
                  const to = draft.dateRange?.[1] ?? from;
                  setDraft({ ...draft, dateRange: from ? [from, to < from ? from : to] : null });
                }}
                className="field mt-1 !px-2 !py-1.5"
              />
            </label>
            <label className="text-xs text-ink-soft">
              To
              <input
                type="date"
                value={draft.dateRange?.[1] ?? ""}
                onChange={(event) => {
                  const to = event.target.value;
                  const from = draft.dateRange?.[0] ?? to;
                  setDraft({ ...draft, dateRange: to ? [from > to ? to : from, to] : null });
                }}
                className="field mt-1 !px-2 !py-1.5"
              />
            </label>
          </div>
        </section>

        <section className="mt-6">
          <h3 className="text-sm font-semibold text-ink">
            Genres
          </h3>
          <div className="mt-2 grid grid-cols-2 gap-1.5">
            {genreOptions.length === 0 && (
              <p className="col-span-2 text-sm text-ink-faint">No genres loaded yet.</p>
            )}
            {genreOptions.map((genre) => (
              <label key={genre} className="flex items-center gap-2 text-sm text-ink">
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
                  className="h-4 w-4 accent-pink"
                />
                <span className="truncate">{genre}</span>
              </label>
            ))}
          </div>
        </section>

        <section className="mt-6">
          <h3 className="text-sm font-semibold text-ink">
            <label htmlFor="filter-distance">Distance</label>
          </h3>
          <p className="mt-0.5 text-sm text-ink-soft">
            {draft.maxDistance !== null
              ? `Within ${(draft.maxDistance / MILES).toFixed(0)} miles`
              : "Any, up to your travel distance"}
          </p>
          <input
            id="filter-distance"
            type="range"
            min={1}
            max={maxMiles}
            value={
              draft.maxDistance !== null
                ? Math.min(maxMiles, Math.round(draft.maxDistance / MILES))
                : maxMiles
            }
            onChange={(event) => {
              const miles = Number(event.target.value);
              setDraft({ ...draft, maxDistance: miles >= maxMiles ? null : miles * MILES });
            }}
            className="mt-2 w-full"
          />
        </section>

        <section className="mt-6">
          <h3 className="text-sm font-semibold text-ink">
            <label htmlFor="filter-price">Price</label>
          </h3>
          {(anyPriced || draft.maxPrice !== null) && (
            <p className="mt-0.5 text-sm text-ink-soft">
              {draft.maxPrice !== null
                ? `Tickets starting at ${(draft.maxPrice / 100).toFixed(0)} dollars or less`
                : "Any price"}
            </p>
          )}
          {anyPriced || draft.maxPrice !== null ? (
            <input
              id="filter-price"
              type="range"
              min={10}
              max={200}
              step={5}
              value={draft.maxPrice !== null ? draft.maxPrice / 100 : 200}
              onChange={(event) => {
                const dollars = Number(event.target.value);
                setDraft({ ...draft, maxPrice: dollars >= 200 ? null : dollars * 100 });
              }}
              className="mt-2 w-full"
            />
          ) : (
            <p className="mt-2 text-sm text-ink-faint">
              None of these shows list a price yet, so there is nothing to filter by.
            </p>
          )}
        </section>

        <div className="mt-8 flex gap-2">
          <button
            type="button"
            onClick={() => apply(draft)}
            className="button-primary flex-1"
          >
            Show results
          </button>
          <button
            type="button"
            onClick={() => apply(EMPTY)}
            className="button-quiet"
          >
            Clear all
          </button>
        </div>
      </aside>
    </>
  );
}
