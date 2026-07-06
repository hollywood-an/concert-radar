"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import type { GeoJSONSource, MapLayerMouseEvent } from "maplibre-gl";
import { useCallback, useMemo, useRef } from "react";
import Map, { Layer, MapRef, Popup, Source } from "react-map-gl/maplibre";

import { eventSelected } from "@/store/mapSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import type { FeedItem } from "@/types";

// Keyless OSM raster style (NEXT_PUBLIC_MAPBOX_TOKEN is unset in this repo). To move to
// Mapbox later: render <Map> from react-map-gl/mapbox with a mapbox:// style + token.
const OSM_STYLE = {
  version: 8 as const,
  glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
  sources: {
    osm: {
      type: "raster" as const,
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster" as const, source: "osm" }],
};

const COLUMBUS = { longitude: -82.9988, latitude: 39.9612, zoom: 10.5 };

interface EventMapProps {
  items: FeedItem[];
  height?: string;
}

export default function EventMap({ items, height = "70vh" }: EventMapProps) {
  const dispatch = useAppDispatch();
  const selectedEventId = useAppSelector((state) => state.map.selectedEventId);
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

  const selected = items.find((item) => item.event_id === selectedEventId) ?? null;

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
    <div style={{ height }} className="overflow-hidden rounded-xl border border-slate-200">
      <Map
        ref={mapRef}
        initialViewState={COLUMBUS}
        mapStyle={OSM_STYLE}
        interactiveLayerIds={["clusters", "event-point"]}
        onClick={handleClick}
        // Guard against a stale container-size read when the map mounts mid-hydration.
        onLoad={(event) => event.target.resize()}
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
              "circle-color": "#4f46e5",
              "circle-opacity": 0.85,
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
              "circle-color": "#e11d48",
              "circle-radius": 7,
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
            <div className="p-1">
              <p className="text-sm font-semibold text-slate-900">{selected.artist_name}</p>
              <p className="text-xs text-slate-600">
                {new Date(selected.starts_at).toLocaleString("en-US", {
                  weekday: "short",
                  month: "short",
                  day: "numeric",
                  hour: "numeric",
                  minute: "2-digit",
                })}
                <br />
                {selected.venue_name}
                {selected.venue_city ? `, ${selected.venue_city}` : ""}
              </p>
              <p className="mt-1 text-xs font-medium text-indigo-700">
                score {selected.score.toFixed(2)}
              </p>
              {selected.source_url && (
                <a
                  href={selected.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 inline-block text-xs font-medium text-indigo-600 hover:underline"
                >
                  Tickets ↗
                </a>
              )}
            </div>
          </Popup>
        )}
      </Map>
    </div>
  );
}
