import { createSlice, PayloadAction } from "@reduxjs/toolkit";

export interface MapBounds {
  ne: [number, number];
  sw: [number, number];
}

export interface MapState {
  bounds: MapBounds | null;
  hoveredEventId: string | null;
  selectedEventId: string | null;
}

const initialState: MapState = { bounds: null, hoveredEventId: null, selectedEventId: null };

const mapSlice = createSlice({
  name: "map",
  initialState,
  reducers: {
    boundsChanged(state, action: PayloadAction<MapBounds>) {
      state.bounds = action.payload;
    },
    eventHovered(state, action: PayloadAction<string | null>) {
      state.hoveredEventId = action.payload;
    },
    eventSelected(state, action: PayloadAction<string | null>) {
      state.selectedEventId = action.payload;
    },
  },
});

export const { boundsChanged, eventHovered, eventSelected } = mapSlice.actions;
export default mapSlice.reducer;
