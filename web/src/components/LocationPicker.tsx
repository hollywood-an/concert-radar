"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import type { MapLayerMouseEvent } from "maplibre-gl";
import { useCallback } from "react";
import Map, { Marker } from "react-map-gl/maplibre";

import type { Location } from "@/types";

const OSM_STYLE = {
  version: 8 as const,
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

interface LocationPickerProps {
  value: Location | null;
  onChange: (location: Location) => void;
}

// Click the map (or drag the marker) to set the home location.
export default function LocationPicker({ value, onChange }: LocationPickerProps) {
  const handleClick = useCallback(
    (event: MapLayerMouseEvent) => {
      onChange({ lat: event.lngLat.lat, lon: event.lngLat.lng });
    },
    [onChange],
  );

  return (
    <div className="h-64 overflow-hidden rounded-xl border border-slate-200">
      <Map
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
  );
}
