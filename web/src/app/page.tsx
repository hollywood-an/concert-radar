"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import ArtistSearchBar from "@/components/ArtistSearchBar";
import FeedList from "@/components/FeedList";
import { ApiError, devLogin, followArtist, listFollows, unfollowArtist } from "@/lib/api";
import type { User } from "@/types";

const TOKEN_KEY = "cr_token";
const USER_KEY = "cr_user";

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [email, setEmail] = useState("");
  const [loginError, setLoginError] = useState<string | null>(null);
  const [loggingIn, setLoggingIn] = useState(false);
  const [followedIds, setFollowedIds] = useState<Set<string>>(new Set());
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set());
  const [feedVersion, setFeedVersion] = useState(0);

  useEffect(() => {
    const storedToken = localStorage.getItem(TOKEN_KEY);
    const storedUser = localStorage.getItem(USER_KEY);
    if (storedToken !== null && storedUser !== null) {
      setToken(storedToken);
      setUser(JSON.parse(storedUser) as User);
    }
    setAuthChecked(true);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setToken(null);
    setUser(null);
    setFollowedIds(new Set());
  }, []);

  useEffect(() => {
    if (token === null) return;
    listFollows(token)
      .then((artists) => setFollowedIds(new Set(artists.map((artist) => artist.id))))
      .catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 401) {
          logout();
        }
      });
  }, [token, logout]);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoggingIn(true);
    setLoginError(null);
    try {
      const auth = await devLogin(email.trim());
      localStorage.setItem(TOKEN_KEY, auth.token);
      localStorage.setItem(USER_KEY, JSON.stringify(auth.user));
      setToken(auth.token);
      setUser(auth.user);
    } catch {
      setLoginError("Login failed. Is the gateway running on localhost:8000?");
    } finally {
      setLoggingIn(false);
    }
  }

  const toggleFollow = useCallback(
    async (artistId: string, followed: boolean) => {
      if (token === null || pendingIds.has(artistId)) return;
      setPendingIds((prev) => new Set(prev).add(artistId));
      try {
        if (followed) {
          await unfollowArtist(token, artistId);
        } else {
          await followArtist(token, artistId);
        }
        setFollowedIds((prev) => {
          const next = new Set(prev);
          if (followed) {
            next.delete(artistId);
          } else {
            next.add(artistId);
          }
          return next;
        });
        setFeedVersion((version) => version + 1);
      } catch (error: unknown) {
        if (error instanceof ApiError && error.status === 401) {
          logout();
        }
      } finally {
        setPendingIds((prev) => {
          const next = new Set(prev);
          next.delete(artistId);
          return next;
        });
      }
    },
    [token, pendingIds, logout],
  );

  if (!authChecked) {
    return null;
  }

  if (token === null || user === null) {
    return (
      <main className="flex min-h-screen items-center justify-center p-6">
        <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
          <h1 className="text-2xl font-bold text-slate-900">Concert Radar</h1>
          <p className="mt-1 text-sm text-slate-500">
            Live shows near you, ranked by your taste.
          </p>
          <form onSubmit={handleLogin} className="mt-6 space-y-3">
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
              disabled={loggingIn}
              className="w-full rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              {loggingIn ? "Signing in…" : "Sign in"}
            </button>
            {loginError && <p className="text-sm text-red-600">{loginError}</p>}
          </form>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto min-h-screen max-w-2xl p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">Concert Radar</h1>
        <div className="flex items-center gap-3 text-sm text-slate-500">
          <span>{user.email}</span>
          <button
            type="button"
            onClick={logout}
            className="font-medium text-indigo-600 hover:underline"
          >
            Sign out
          </button>
        </div>
      </header>
      <div className="mt-6">
        <ArtistSearchBar
          token={token}
          followedIds={followedIds}
          pendingIds={pendingIds}
          onToggleFollow={toggleFollow}
        />
      </div>
      <section className="mt-6">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Upcoming near you
        </h2>
        <FeedList
          token={token}
          followedIds={followedIds}
          pendingIds={pendingIds}
          onToggleFollow={toggleFollow}
          refreshKey={feedVersion}
          onAuthError={logout}
        />
      </section>
    </main>
  );
}
