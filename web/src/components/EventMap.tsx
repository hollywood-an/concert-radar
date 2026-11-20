"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import type { GeoJSONSource, MapLayerMouseEvent } from "maplibre-gl";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Map, { Layer, MapRef, Popup, Source } from "react-map-gl/maplibre";

import { useRecordActivity } from "@/hooks/useRecordActivity";
import { formatDate, formatMatch } from "@/lib/format";
import { OSM_STYLE } from "@/lib/mapStyle";
import { eventSelected } from "@/store/mapSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import type { FeedItem } from "@/types";

// Fallback view for an account without a saved home location.
const COLUMBUS = { longitude: -82.9988, latitude: 39.9612, zoom: 10.5 };

interface EventMapProps {
  items: FeedItem[];
  height?: string;
}

export default function EventMap({ items, height = "70vh" }: EventMapProps) {
  const dispatch = useAppDispatch();
  const record = useRecordActivity();
  const selectedEventId = useAppSelector((state) => state.map.selectedEventId);
  const followCount = useAppSelector((state) => state.follows.artistIds.length);
  const home = useAppSelector((state) => state.auth.user?.home_location ?? null);
  const mapRef = useRef<MapRef | null>(null);

  const geojson = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: items.map((item) => ({
        type: "Feature" as const,
        properties: { event_id: item.event_id },
        geometry: {
          type: "Point" as const,
          coordinates: [item.venue_lon, item.venue_lat],
        },
      })),
    }),
    [items],
  );

  // Frame every loaded show once per result set (a new filter or a new home location),
  // without yanking the view back while the user pans around.
  const [mapLoaded, setMapLoaded] = useState(false);
  const fitKey = useMemo(
    () => items.map((item) => item.event_id).join(","),
    [items],
  );
  useEffect(() => {
    const map = mapRef.current;
    if (!mapLoaded || map === null || items.length === 0) {
      return;
    }
    let west = Infinity;
    let south = Infinity;
    let east = -Infinity;
    let north = -Infinity;
    for (const item of items) {
      west = Math.min(west, item.venue_lon);
      east = Math.max(east, item.venue_lon);
      south = Math.min(south, item.venue_lat);
      north = Math.max(north, item.venue_lat);
    }
    map.fitBounds(
      [
        [west, south],
        [east, north],
      ],
      { padding: 60, maxZoom: 13, duration: 0 },
    );
    // items is read through fitKey so appended pages of the same result set refit too.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey, mapLoaded]);

  const selected = items.find((item) => item.event_id === selectedEventId) ?? null;
  const selectedMatch = selected === null ? null : formatMatch(selected.score, followCount);

  const handleClick = useCallback(
    (event: MapLayerMouseEvent) => {
      const feature = event.features?.[0];
      const map = mapRef.current;
      if (!feature || !map) {
        dispatch(eventSelected(null));
        return;
      }
      const clusterId: unknown = feature.properties?.cluster_id;
      if (typeof clusterId === "number") {
        const source = map.getSource("events") as GeoJSONSource;
        void source.getClusterExpansionZoom(clusterId).then((zoom) => {
          const [lng, lat] = (feature.geometry as GeoJSON.Point).coordinates;
          map.easeTo({ center: [lng, lat], zoom });
        });
        return;
      }
      const eventId: unknown = feature.properties?.event_id;
      if (typeof eventId === "string") {
        dispatch(eventSelected(eventId));
      }
    },
    [dispatch],
  );

  return (
    <div style={{ height }} className="overflow-hidden rounded-[0.625rem] border-2 border-ink">
      <Map
        ref={mapRef}
        initialViewState={
          home === null ? COLUMBUS : { longitude: home.lon, latitude: home.lat, zoom: 10.5 }
        }
        mapStyle={OSM_STYLE}
        interactiveLayerIds={["clusters", "event-point"]}
        onClick={handleClick}
        // Guard against a stale container-size read when the map mounts mid-hydration.
        onLoad={(event) => {
          event.target.resize();
          setMapLoaded(true);
        }}
        style={{ width: "100%", height: "100%" }}
      >
        <Source
          id="events"
          type="geojson"
          data={geojson}
          cluster
          clusterMaxZoom={13}
          clusterRadius={45}
        >
          <Layer
            id="clusters"
            type="circle"
            filter={["has", "point_count"]}
            paint={{
              "circle-color": "#1B1A4B",
              "circle-opacity": 0.92,
              "circle-radius": ["step", ["get", "point_count"], 16, 10, 22, 25, 28],
            }}
          />
          <Layer
            id="cluster-count"
            type="symbol"
            filter={["has", "point_count"]}
            layout={{
              "text-field": ["get", "point_count_abbreviated"],
              "text-size": 13,
            }}
            paint={{ "text-color": "#ffffff" }}
          />
          <Layer
            id="event-point"
            type="circle"
            filter={["!", ["has", "point_count"]]}
            paint={{
              "circle-color": "#E3126B",
              "circle-radius": 8,
              "circle-stroke-width": 2,
              "circle-stroke-color": "#ffffff",
            }}
          />
        </Source>
        {selected && (
          <Popup
            longitude={selected.venue_lon}
            latitude={selected.venue_lat}
            anchor="bottom"
            offset={12}
            onClose={() => dispatch(eventSelected(null))}
            closeOnClick={false}
            maxWidth="320px"
          >
            <div className="font-sans text-ink">
              <p className="font-display text-xl font-extrabold leading-tight">
                {selected.artist_name}
              </p>
              <p className="mt-1 text-xs">
                <span className="font-semibold">{formatDate(selected.starts_at)}</span>
                <br />
                <span className="text-ink-soft">
                  {selected.venue_name}
                  {selected.venue_city ? `, ${selected.venue_city}` : ""}
                </span>
              </p>
              {selectedMatch && (
                <p className="mt-1.5 text-xs font-semibold text-pink-deep">{selectedMatch}</p>
              )}
              <p className="mt-2 flex gap-4 text-xs">
                <Link href={`/event/${selected.event_id}`} className="link">
                  Show details
                </Link>
                {selected.source_url && (
                  <a
                    href={selected.source_url}
                    target="_blank"
                    rel="noreferrer"
                    onClick={() => record("ticket_click", selected.event_id)}
                    className="link"
                  >
                    Get tickets<span className="sr-only"> (opens in a new tab)</span>
                  </a>
                )}
              </p>
            </div>
          </Popup>
        )}
      </Map>
    </div>
  );
}
