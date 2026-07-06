import { createAsyncThunk, createSlice, PayloadAction } from "@reduxjs/toolkit";

import { dismissEvent as apiDismissEvent, getFeed } from "@/lib/api";
import type { FeedFilters, FeedItem, FeedPage } from "@/types";
import type { RootState } from "@/store/store";

export interface FeedState {
  items: FeedItem[];
  cursor: string | null;
  hasMore: boolean;
  status: "idle" | "loading" | "error";
  filters: FeedFilters;
  freshEventIds: string[];
}

const initialState: FeedState = {
  items: [],
  cursor: null,
  hasMore: false,
  status: "idle",
  filters: { dateRange: null, genres: [], maxDistance: null, maxPrice: null },
  freshEventIds: [],
};

export const fetchFeedPage = createAsyncThunk<
  FeedPage,
  { reset: boolean },
  { state: RootState }
>("feed/fetchPage", async ({ reset }, thunkApi) => {
  const { auth, feed } = thunkApi.getState();
  if (auth.token === null) {
    throw new Error("not authenticated");
  }
  return getFeed(auth.token, reset ? null : feed.cursor, feed.filters);
});

// Walk the remaining pages so the map has every in-radius event (bounded by page cap).
export const fetchEntireFeed = createAsyncThunk<void, void, { state: RootState }>(
  "feed/fetchEntire",
  async (_, thunkApi) => {
    await thunkApi.dispatch(fetchFeedPage({ reset: true })).unwrap();
    for (let page = 0; page < 10; page += 1) {
      const { feed } = thunkApi.getState();
      if (!feed.hasMore) {
        return;
      }
      await thunkApi.dispatch(fetchFeedPage({ reset: false })).unwrap();
    }
  },
);

export const dismissEvent = createAsyncThunk<string, string, { state: RootState }>(
  "feed/dismiss",
  async (eventId, thunkApi) => {
    const { auth } = thunkApi.getState();
    if (auth.token === null) {
      throw new Error("not authenticated");
    }
    await apiDismissEvent(auth.token, eventId);
    return eventId;
  },
);

const feedSlice = createSlice({
  name: "feed",
  initialState,
  reducers: {
    filtersChanged(state, action: PayloadAction<FeedFilters>) {
      state.filters = action.payload;
      state.items = [];
      state.cursor = null;
      state.hasMore = false;
      state.freshEventIds = [];
    },
    matchReceived(state, action: PayloadAction<FeedItem>) {
      const item = action.payload;
      if (state.items.some((existing) => existing.event_id === item.event_id)) {
        return;
      }
      state.items.unshift(item);
      state.freshEventIds.push(item.event_id);
    },
    feedCleared() {
      return initialState;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchFeedPage.pending, (state, action) => {
        if (action.meta.arg.reset) {
          state.status = "loading";
        }
      })
      .addCase(fetchFeedPage.fulfilled, (state, action) => {
        const page = action.payload;
        state.items = action.meta.arg.reset ? page.items : [...state.items, ...page.items];
        state.cursor = page.next_cursor;
        state.hasMore = page.has_more;
        state.status = "idle";
        if (action.meta.arg.reset) {
          state.freshEventIds = [];
        }
      })
      .addCase(fetchFeedPage.rejected, (state) => {
        state.status = "error";
      })
      .addCase(dismissEvent.fulfilled, (state, action) => {
        state.items = state.items.filter((item) => item.event_id !== action.payload);
        state.freshEventIds = state.freshEventIds.filter((id) => id !== action.payload);
      });
  },
});

export const { filtersChanged, matchReceived, feedCleared } = feedSlice.actions;
export default feedSlice.reducer;
