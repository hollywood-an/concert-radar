"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef } from "react";

import EventCard from "@/components/EventCard";
import { activeFilterCount } from "@/components/FilterDrawer";
import { fetchFeedPage } from "@/store/feedSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

function Skeleton() {
  return (
    <div className="ticket-shadow">
      <div className="ticket animate-pulse">
        <div className="ticket-stub h-[7.25rem]" />
        <div className="flex-1 space-y-3 p-4">
          <div className="h-6 w-2/5 rounded bg-stub" />
          <div className="h-3.5 w-3/5 rounded bg-paper" />
          <div className="h-5 w-1/3 rounded-full bg-paper" />
        </div>
      </div>
    </div>
  );
}

export default function FeedList() {
  const dispatch = useAppDispatch();
  const { items, hasMore, status, freshEventIds, filters } = useAppSelector(
    (state) => state.feed,
  );
  const loadingMore = useRef(false);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  const loadMore = useCallback(() => {
    if (loadingMore.current || !hasMore) {
      return;
    }
    loadingMore.current = true;
    void dispatch(fetchFeedPage({ reset: false })).finally(() => {
      loadingMore.current = false;
    });
  }, [dispatch, hasMore]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || !hasMore) {
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        loadMore();
      }
    });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, loadMore]);

  if (status === "loading") {
    return (
      <div className="space-y-3" aria-busy="true" aria-label="Loading shows">
        <Skeleton />
        <Skeleton />
        <Skeleton />
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="rounded-[0.625rem] border border-red-200 bg-red-50 p-5 text-sm text-red-900">
        <p className="font-semibold">The feed didn&apos;t load.</p>
        <p className="mt-1">The server may be restarting or offline.</p>
        <button
          type="button"
          onClick={() => void dispatch(fetchFeedPage({ reset: true }))}
          className="button-quiet mt-3"
        >
          Try again
        </button>
      </div>
    );
  }

  if (items.length === 0) {
    const filtered = activeFilterCount(filters) > 0;
    return (
      <div className="rounded-[0.625rem] border border-dashed border-ink/25 p-8 text-center">
        <p className="font-display text-2xl font-extrabold">
          {filtered ? "No shows match these filters" : "No shows in range yet"}
        </p>
        <p className="mx-auto mt-2 max-w-sm text-sm text-ink-soft">
          {filtered ? (
            "Clear a filter or widen the date range to see more."
          ) : (
            <>
              Shows are listed around Columbus, Ohio for now. Move your home location there or
              widen your travel radius in{" "}
              <Link href="/settings" className="link">
                Settings
              </Link>
              .
            </>
          )}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {items.map((item) => (
        <EventCard
          key={item.event_id}
          item={item}
          fresh={freshEventIds.includes(item.event_id)}
        />
      ))}
      {hasMore && (
        <div ref={sentinelRef} className="py-3 text-center">
          <button type="button" onClick={loadMore} className="button-quiet">
            Show more
          </button>
        </div>
      )}
    </div>
  );
}
