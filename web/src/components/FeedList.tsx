"use client";

import { useCallback, useEffect, useRef } from "react";

import EventCard from "@/components/EventCard";
import { fetchFeedPage } from "@/store/feedSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

function Skeleton() {
  return (
    <div className="flex animate-pulse gap-4 rounded-xl border border-slate-200 bg-white p-4">
      <div className="h-24 w-24 flex-none rounded-lg bg-slate-200" />
      <div className="flex-1 space-y-3 py-2">
        <div className="h-4 w-1/3 rounded bg-slate-200" />
        <div className="h-3 w-1/2 rounded bg-slate-200" />
        <div className="h-3 w-2/3 rounded bg-slate-200" />
      </div>
    </div>
  );
}

export default function FeedList() {
  const dispatch = useAppDispatch();
  const { items, hasMore, status, freshEventIds } = useAppSelector((state) => state.feed);
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
      <div className="space-y-3">
        <Skeleton />
        <Skeleton />
        <Skeleton />
      </div>
    );
  }

  if (status === "error") {
    return (
      <p className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        Could not load your feed. Is the gateway running on localhost:8000?
      </p>
    );
  }

  if (items.length === 0) {
    return (
      <p className="rounded-xl border border-slate-200 bg-white p-6 text-center text-sm text-slate-500">
        No upcoming shows match. Loosen the filters or run the scraper to pull in events.
      </p>
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
        <div ref={sentinelRef} className="py-2 text-center">
          <button
            type="button"
            onClick={loadMore}
            className="text-sm font-medium text-indigo-600 hover:underline"
          >
            Load more
          </button>
        </div>
      )}
    </div>
  );
}
