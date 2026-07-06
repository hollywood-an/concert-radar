"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import LocationPicker from "@/components/LocationPicker";
import NavBar from "@/components/NavBar";
import SpotifyImportButton from "@/components/SpotifyImportButton";
import { patchMe } from "@/lib/api";
import { adoptToken, userUpdated } from "@/store/authSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { prefsLoaded, savePrefs } from "@/store/notificationsSlice";
import type { Location } from "@/types";

const MILES = 1609.34;

function SettingsForm() {
  const dispatch = useAppDispatch();
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = useAppSelector((state) => state.auth.token);
  const user = useAppSelector((state) => state.auth.user);

  const [location, setLocation] = useState<Location | null>(null);
  const [radiusMiles, setRadiusMiles] = useState(50);
  const [emailAlerts, setEmailAlerts] = useState(true);
  const [quietStart, setQuietStart] = useState("");
  const [quietEnd, setQuietEnd] = useState("");
  const [saved, setSaved] = useState(false);
  const [importedBanner, setImportedBanner] = useState<number | null>(null);

  // The Spotify callback proxy lands here with ?token=...&imported=N.
  useEffect(() => {
    const callbackToken = searchParams.get("token");
    const imported = searchParams.get("imported");
    if (callbackToken !== null) {
      void dispatch(adoptToken(callbackToken));
      if (imported !== null) {
        setImportedBanner(Number(imported));
      }
      router.replace("/settings");
    }
  }, [searchParams, dispatch, router]);

  useEffect(() => {
    if (user !== null) {
      setLocation(user.home_location);
      setRadiusMiles(Math.round(user.travel_radius_m / MILES));
      setEmailAlerts(user.alert_email ?? true);
      setQuietStart(user.quiet_hours_start?.slice(0, 5) ?? "");
      setQuietEnd(user.quiet_hours_end?.slice(0, 5) ?? "");
      dispatch(prefsLoaded(user));
    }
  }, [user, dispatch]);

  if (token === null || user === null) {
    return (
      <p className="mt-10 text-center text-sm text-slate-500">
        Sign in on the Feed page to manage settings.
      </p>
    );
  }

  const save = async () => {
    setSaved(false);
    const updated = await patchMe(token, {
      home_location: location,
      travel_radius_m: Math.round(radiusMiles * MILES),
    });
    dispatch(userUpdated(updated));
    await dispatch(
      savePrefs({
        email: emailAlerts,
        quietHoursStart: quietStart === "" ? null : `${quietStart}:00`,
        quietHoursEnd: quietEnd === "" ? null : `${quietEnd}:00`,
      }),
    );
    setSaved(true);
  };

  return (
    <>
      {importedBanner !== null && (
        <p className="mt-6 rounded-xl border border-green-200 bg-green-50 p-4 text-sm text-green-800">
          Imported {importedBanner} artists from Spotify. Your feed is re-ranking now.
        </p>
      )}

      <section className="mt-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Home location
        </h2>
        <p className="mt-1 text-sm text-slate-500">
          Click the map or drag the pin to set where shows should be near.
        </p>
        <div className="mt-3">
          <LocationPicker value={location} onChange={setLocation} />
        </div>
        {location && (
          <p className="mt-2 text-xs text-slate-500">
            {location.lat.toFixed(4)}, {location.lon.toFixed(4)}
          </p>
        )}
      </section>

      <section className="mt-8">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Travel radius — {radiusMiles} mi
        </h2>
        <input
          type="range"
          min={1}
          max={150}
          value={radiusMiles}
          onChange={(event) => setRadiusMiles(Number(event.target.value))}
          className="mt-3 w-full accent-indigo-600"
        />
      </section>

      <section className="mt-8">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Alerts
        </h2>
        <label className="mt-3 flex items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={emailAlerts}
            onChange={(event) => setEmailAlerts(event.target.checked)}
            className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
          />
          Email me when a matching show is announced
        </label>
        <div className="mt-3 flex items-center gap-2 text-sm text-slate-700">
          <span>Quiet hours</span>
          <input
            type="time"
            value={quietStart}
            onChange={(event) => setQuietStart(event.target.value)}
            className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
          />
          <span className="text-slate-400">–</span>
          <input
            type="time"
            value={quietEnd}
            onChange={(event) => setQuietEnd(event.target.value)}
            className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
          />
          {(quietStart !== "" || quietEnd !== "") && (
            <button
              type="button"
              onClick={() => {
                setQuietStart("");
                setQuietEnd("");
              }}
              className="text-xs font-medium text-indigo-600 hover:underline"
            >
              clear
            </button>
          )}
        </div>
      </section>

      <section className="mt-8">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Spotify
        </h2>
        <p className="mt-1 text-sm text-slate-500">
          Import the artists you follow to seed your taste profile.
        </p>
        <div className="mt-3">
          <SpotifyImportButton />
        </div>
      </section>

      <div className="mt-10 flex items-center gap-3">
        <button
          type="button"
          onClick={() => void save()}
          className="rounded-xl bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500"
        >
          Save settings
        </button>
        {saved && <span className="text-sm font-medium text-green-600">Saved ✓</span>}
      </div>
    </>
  );
}

export default function SettingsPage() {
  return (
    <main className="mx-auto min-h-screen max-w-2xl p-6">
      <NavBar />
      <Suspense fallback={null}>
        <SettingsForm />
      </Suspense>
    </main>
  );
}
