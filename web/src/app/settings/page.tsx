"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { useSessionReady } from "@/app/providers";
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
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const sessionReady = useSessionReady();
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
      dispatch(prefsLoaded(user));
    }
  }, [user, dispatch]);

  if (token === null || user === null) {
    return (
      <p className="mt-10 text-center text-sm text-ink-soft">
        {sessionReady ? (
          <>
            <Link href="/" className="link">
              Sign in
            </Link>{" "}
            to manage settings.
          </>
        ) : (
          "Loading…"
        )}
      </p>
    );
  }

  const save = async () => {
    setSaveState("saving");
    try {
      const updated = await patchMe(token, {
        home_location: location,
        travel_radius_m: Math.round(radiusMiles * MILES),
      });
      dispatch(userUpdated(updated));
      await dispatch(savePrefs({ email: emailAlerts })).unwrap();
      setSaveState("saved");
    } catch {
      setSaveState("error");
    }
  };

  // Any edit after a save means the form no longer matches what was saved.
  const edited = <T,>(set: (value: T) => void) => (value: T) => {
    set(value);
    setSaveState("idle");
  };

  return (
    <>
      {importedBanner !== null && (
        <p role="status" className="mt-6 rounded-[0.625rem] bg-highlighter p-4 text-sm font-medium">
          Imported {importedBanner} {importedBanner === 1 ? "artist" : "artists"} from Spotify.
          Your feed is re-sorting around them now.
        </p>
      )}

      <h1 className="heading mt-8 !text-5xl">Settings</h1>

      <section className="mt-8">
        <h2 className="heading !text-2xl">Home location</h2>
        <p className="mt-1.5 text-sm text-ink-soft">
          Shows are measured from here. Search for an address, click the map, or drag the pin.
        </p>
        <div className="mt-3">
          <LocationPicker value={location} onChange={edited(setLocation)} />
        </div>
      </section>

      <section className="mt-8">
        <h2 className="heading !text-2xl">
          <label htmlFor="radius">How far you&apos;ll travel</label>
        </h2>
        <p className="mt-1.5 text-sm text-ink-soft">
          Shows within <span className="font-semibold text-ink">{radiusMiles} miles</span> of
          your home location appear in your feed and on the map.
        </p>
        <input
          id="radius"
          type="range"
          min={1}
          max={150}
          value={radiusMiles}
          onChange={(event) => edited(setRadiusMiles)(Number(event.target.value))}
          className="mt-3 w-full"
        />
      </section>

      <section className="mt-8">
        <h2 className="heading !text-2xl">Alerts</h2>
        <label className="mt-3 flex items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            checked={emailAlerts}
            onChange={(event) => edited(setEmailAlerts)(event.target.checked)}
            className="h-4 w-4 accent-pink"
          />
          Email me a daily digest when artists I follow have shows near me
        </label>
        <p className="mt-1 pl-6 text-xs text-ink-soft">
          Sent once a day at 14:00 UTC (10am Eastern in summer, 9am in winter).
        </p>
      </section>

      <section className="mt-8">
        <h2 className="heading !text-2xl">Spotify</h2>
        <p className="mt-1.5 text-sm text-ink-soft">
          Bring in the artists you follow on Spotify, so your feed is ranked from day one.
        </p>
        <div className="mt-3">
          <SpotifyImportButton />
        </div>
      </section>

      <div className="mt-10 flex items-center gap-3">
        <button
          type="button"
          onClick={() => void save()}
          disabled={saveState === "saving"}
          className="button-primary"
        >
          {saveState === "saving" ? "Saving…" : "Save settings"}
        </button>
        <span role="status" className="text-sm font-medium">
          {saveState === "saved" && <span className="text-emerald-800">Settings saved</span>}
          {saveState === "error" && (
            <span className="text-red-700">
              Couldn&apos;t save. Check your connection and try again.
            </span>
          )}
        </span>
      </div>
    </>
  );
}

export default function SettingsPage() {
  return (
    <main className="mx-auto min-h-screen max-w-3xl px-4 pb-16 pt-6 sm:px-6">
      <NavBar />
      <Suspense fallback={null}>
        <SettingsForm />
      </Suspense>
    </main>
  );
}
