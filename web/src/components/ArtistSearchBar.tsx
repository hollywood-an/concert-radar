"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import FollowButton from "@/components/FollowButton";
import { searchArtists } from "@/lib/api";
import { toggleFollow } from "@/store/followsSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import type { ArtistSummary } from "@/types";

export default function ArtistSearchBar() {
  const dispatch = useAppDispatch();
  const token = useAppSelector((state) => state.auth.token);
  const followedIds = useAppSelector((state) => state.follows.artistIds);
  const pendingIds = useAppSelector((state) => state.follows.pendingToggles);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ArtistSummary[]>([]);
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed === "" || token === null) {
      setResults([]);
      setOpen(false);
      setSearching(false);
      return;
    }
    setSearching(true);
    const timer = setTimeout(() => {
      searchArtists(token, trimmed)
        .then((artists) => {
          setResults(artists);
          setOpen(true);
        })
        .catch(() => setResults([]))
        .finally(() => setSearching(false));
    }, 300);
    return () => clearTimeout(timer);
  }, [query, token]);

  useEffect(() => {
    function handleClick(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <div ref={containerRef} className="relative">
      <input
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onFocus={() => {
          if (results.length > 0) setOpen(true);
        }}
        placeholder="Search artists to follow…"
        aria-label="Search artists to follow"
        className="field !rounded-full !px-5"
      />
      {searching && (
        <span className="absolute right-10 top-2.5 text-sm text-ink-faint">Searching…</span>
      )}
      {open && (
        <ul className="absolute z-20 mt-2 max-h-80 w-full overflow-auto rounded-[0.625rem] border border-line bg-sheet py-1 shadow-lg">
          {results.length === 0 ? (
            <li className="px-4 py-3 text-sm text-ink-soft">
              No artist found by that name. Check the spelling, or try another.
            </li>
          ) : (
            results.map((artist) => (
              <li
                key={artist.id}
                className="flex items-center justify-between gap-3 px-4 py-2.5 hover:bg-paper"
              >
                <div className="min-w-0">
                  <Link
                    href={`/artist/${artist.id}`}
                    className="block truncate font-display text-lg font-extrabold leading-tight text-ink hover:text-pink"
                  >
                    {artist.name}
                  </Link>
                  {artist.genres.length > 0 && (
                    <p className="truncate text-xs text-ink-soft">
                      {artist.genres.slice(0, 5).join(", ")}
                    </p>
                  )}
                </div>
                <FollowButton
                  followed={followedIds.includes(artist.id)}
                  pending={pendingIds.includes(artist.id)}
                  onToggle={() =>
                    void dispatch(
                      toggleFollow({
                        artistId: artist.id,
                        followed: followedIds.includes(artist.id),
                      }),
                    )
                  }
                />
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
