"use client";

import { useState } from "react";

import { ApiError, spotifyLogin } from "@/lib/api";
import { useAppSelector } from "@/store/hooks";

// Kicks off the OAuth redirect; the gateway answers 503 until Spotify credentials
// are configured in .env, which we surface instead of a broken redirect.
export default function SpotifyImportButton() {
  const token = useAppSelector((state) => state.auth.token);
  const [unconfigured, setUnconfigured] = useState(false);
  const [starting, setStarting] = useState(false);

  const start = async () => {
    if (token === null) {
      return;
    }
    setStarting(true);
    try {
      const { authorize_url } = await spotifyLogin(token);
      window.location.assign(authorize_url);
    } catch (error: unknown) {
      if (error instanceof ApiError && error.status === 503) {
        setUnconfigured(true);
      }
      setStarting(false);
    }
  };

  return (
    <div>
      <button
        type="button"
        onClick={() => void start()}
        disabled={starting || unconfigured}
        className="flex items-center gap-2 rounded-xl bg-[#1DB954] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#1aa64b] disabled:opacity-50"
      >
        <svg viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4">
          <path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0Zm5.5 17.34a.75.75 0 0 1-1.03.25c-2.82-1.72-6.37-2.11-10.55-1.16a.75.75 0 1 1-.33-1.46c4.57-1.05 8.5-.6 11.66 1.34.35.22.46.68.25 1.03Zm1.47-3.27a.94.94 0 0 1-1.29.31c-3.23-1.98-8.15-2.56-11.97-1.4a.94.94 0 1 1-.55-1.79c4.37-1.33 9.79-.68 13.5 1.6.44.27.58.85.31 1.28Zm.13-3.4C15.24 8.37 8.9 8.15 5.2 9.28a1.12 1.12 0 1 1-.66-2.15c4.25-1.3 11.28-1.05 15.72 1.6a1.13 1.13 0 0 1-1.16 1.94Z" />
        </svg>
        {starting ? "Redirecting…" : "Import from Spotify"}
      </button>
      {unconfigured && (
        <p className="mt-2 text-xs text-slate-500">
          Spotify isn&apos;t configured yet — set SPOTIFY_CLIENT_ID and
          SPOTIFY_CLIENT_SECRET in .env, then restart the gateway.
        </p>
      )}
    </div>
  );
}
