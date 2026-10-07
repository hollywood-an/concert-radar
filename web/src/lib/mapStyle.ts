import type { StyleSpecification } from "maplibre-gl";

// Keyless OSM raster style (NEXT_PUBLIC_MAPBOX_TOKEN is unset in this repo). To move to
// Mapbox later: render <Map> from react-map-gl/mapbox with a mapbox:// style + token.
// The glyphs are for EventMap's cluster-count labels.
export const OSM_STYLE: StyleSpecification = {
  version: 8,
  glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};
