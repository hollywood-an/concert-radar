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
  // Bumped whenever the list starts over (a reset or a filter change). A response that
  // was requested under an older generation is dropped instead of overwriting newer data.
  generation: number;
}

const initialState: FeedState = {
  items: [],
  cursor: null,
  hasMore: false,
  status: "idle",
  filters: { dateRange: null, genres: [], maxDistance: null, maxPrice: null },
  freshEventIds: [],
  generation: 0,
};

export const fetchFeedPage = createAsyncThunk<
  FeedPage,
  { reset: boolean },
  { state: RootState; fulfilledMeta: { generation: number } }
>("feed/fetchPage", async ({ reset }, thunkApi) => {
  // The pending reducer has already run, so a reset sees its own new generation here.
  const { auth, feed } = thunkApi.getState();
  if (auth.token === null) {
    throw new Error("not authenticated");
  }
  const page = await getFeed(auth.token, reset ? null : feed.cursor, feed.filters);
  return thunkApi.fulfillWithValue(page, { generation: feed.generation });
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
      state.generation += 1;
    },
    matchReceived(state, action: PayloadAction<FeedItem>) {
      const item = action.payload;
      if (state.items.some((existing) => existing.event_id === item.event_id)) {
        return;
      }
      state.items.unshift(item);
      state.freshEventIds.push(item.event_id);
    },
    feedCleared(state) {
      // Keep counting up so a response still in flight from the old session is dropped.
      return { ...initialState, generation: state.generation + 1 };
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchFeedPage.pending, (state, action) => {
        if (action.meta.arg.reset) {
          state.status = "loading";
          state.generation += 1;
        }
      })
      .addCase(fetchFeedPage.fulfilled, (state, action) => {
        if (action.meta.generation !== state.generation) {
          return;
        }
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
