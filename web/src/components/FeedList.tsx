"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import EventCard from "@/components/EventCard";
import { ApiError, getFeed } from "@/lib/api";
import type { FeedItem } from "@/types";

interface FeedListProps {
  token: string;
  followedIds: Set<string>;
  pendingIds: Set<string>;
  onToggleFollow: (artistId: string, followed: boolean) => void;
  refreshKey: number;
  onAuthError: () => void;
}

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

export default function FeedList({
  token,
  followedIds,
  pendingIds,
  onToggleFollow,
  refreshKey,
  onAuthError,
}: FeedListProps) {
  const [items, setItems] = useState<FeedItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const loadingMoreRef = useRef(false);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    getFeed(token, null)
      .then((page) => {
        if (cancelled) return;
        setItems(page.items);
        setCursor(page.next_cursor);
        setHasMore(page.has_more);
        setStatus("ready");
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (error instanceof ApiError && error.status === 401) {
          onAuthError();
          return;
        }
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [token, refreshKey, onAuthError]);

  const loadMore = useCallback(() => {
    if (loadingMoreRef.current || cursor === null) return;
    loadingMoreRef.current = true;
    getFeed(token, cursor)
      .then((page) => {
        setItems((prev) => [...prev, ...page.items]);
        setCursor(page.next_cursor);
        setHasMore(page.has_more);
      })
      .catch(() => setStatus("error"))
      .finally(() => {
        loadingMoreRef.current = false;
      });
  }, [token, cursor]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || !hasMore) return;
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
        No upcoming shows near you yet. Run the scraper to pull in events.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {items.map((item) => (
        <EventCard
          key={item.event_id}
          item={item}
          followed={followedIds.has(item.artist_id)}
          pending={pendingIds.has(item.artist_id)}
          onToggleFollow={onToggleFollow}
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
