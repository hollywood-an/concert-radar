"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import type { MapLayerMouseEvent } from "maplibre-gl";
import { type FormEvent, useCallback, useRef, useState } from "react";
import Map, { MapRef, Marker } from "react-map-gl/maplibre";

import { geocode } from "@/lib/api";
import { OSM_STYLE } from "@/lib/mapStyle";
import { useAppSelector } from "@/store/hooks";
import type { GeocodeResult, Location } from "@/types";

interface LocationPickerProps {
  value: Location | null;
  onChange: (location: Location) => void;
}

// Search for an address, click the map, or drag the marker to set the home location.
// Search runs on submit only: Nominatim's usage policy rules out search-as-you-type.
export default function LocationPicker({ value, onChange }: LocationPickerProps) {
  const token = useAppSelector((state) => state.auth.token);
  const mapRef = useRef<MapRef | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GeocodeResult[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(false);

  const handleClick = useCallback(
    (event: MapLayerMouseEvent) => {
      onChange({ lat: event.lngLat.lat, lon: event.lngLat.lng });
    },
    [onChange],
  );

  const search = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (trimmed.length < 3 || token === null) {
      return;
    }
    setSearching(true);
    setSearchError(false);
    try {
      setResults(await geocode(token, trimmed));
    } catch {
      setResults(null);
      setSearchError(true);
    } finally {
      setSearching(false);
    }
  };

  const choose = (place: GeocodeResult) => {
    onChange({ lat: place.lat, lon: place.lon });
    mapRef.current?.flyTo({ center: [place.lon, place.lat], zoom: 11 });
    setQuery(place.label);
    setResults(null);
  };

  return (
    <div>
      <form onSubmit={(event) => void search(event)} className="flex gap-2">
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search for an address or city"
          aria-label="Search for an address or city"
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={searching || query.trim().length < 3}
          className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          {searching ? "Searching…" : "Search"}
        </button>
      </form>
      {searchError && (
        <p className="mt-2 text-sm text-amber-700">
          Address search is unavailable right now. Click the map instead.
        </p>
      )}
      {results !== null && (
        <ul className="mt-2 divide-y divide-slate-100 rounded-lg border border-slate-200">
          {results.length === 0 && (
            <li className="px-3 py-2 text-sm text-slate-500">No places found.</li>
          )}
          {results.map((place) => (
            <li key={`${place.lat},${place.lon}`}>
              <button
                type="button"
                onClick={() => choose(place)}
                className="w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
              >
                {place.label}
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-3 h-64 overflow-hidden rounded-xl border border-slate-200">
        <Map
          ref={mapRef}
          initialViewState={{
            longitude: value?.lon ?? -82.9988,
            latitude: value?.lat ?? 39.9612,
            zoom: 10,
          }}
          mapStyle={OSM_STYLE}
          onClick={handleClick}
          // Guard against a stale container-size read when the map mounts mid-hydration.
          onLoad={(event) => event.target.resize()}
          style={{ width: "100%", height: "100%" }}
        >
          {value && (
            <Marker
              longitude={value.lon}
              latitude={value.lat}
              draggable
              onDragEnd={(event) =>
                onChange({ lat: event.lngLat.lat, lon: event.lngLat.lng })
              }
              color="#4f46e5"
            />
          )}
        </Map>
      </div>
    </div>
  );
}
