"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import Map, { Marker } from "react-map-gl/maplibre";

import { OSM_STYLE } from "@/lib/mapStyle";
import type { Location } from "@/types";

export default function VenueMap({ location }: { location: Location }) {
  return (
    <div className="h-56 overflow-hidden rounded-[0.625rem] border border-line">
      <Map
        initialViewState={{ longitude: location.lon, latitude: location.lat, zoom: 14 }}
        mapStyle={OSM_STYLE}
        // Keeps a page scroll that passes over the map from zooming it.
        cooperativeGestures
        // Guard against a stale container-size read when the map mounts mid-hydration.
        onLoad={(event) => event.target.resize()}
        style={{ width: "100%", height: "100%" }}
      >
        <Marker longitude={location.lon} latitude={location.lat} color="#E3126B" />
      </Map>
    </div>
  );
}
