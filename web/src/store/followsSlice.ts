import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";

import { followArtist, listFollows, unfollowArtist } from "@/lib/api";
import { fetchFeedPage } from "@/store/feedSlice";
import type { RootState } from "@/store/store";

export interface FollowsState {
  artistIds: string[];
  pendingToggles: string[];
}

const initialState: FollowsState = { artistIds: [], pendingToggles: [] };

export const loadFollows = createAsyncThunk<string[], void, { state: RootState }>(
  "follows/load",
  async (_, thunkApi) => {
    const { auth } = thunkApi.getState();
    if (auth.token === null) {
      throw new Error("not authenticated");
    }
    const artists = await listFollows(auth.token);
    return artists.map((artist) => artist.id);
  },
);

// Optimistic toggle per the spec: flip immediately, revert on failure, then re-rank.
export const toggleFollow = createAsyncThunk<void, string, { state: RootState }>(
  "follows/toggle",
  async (artistId, thunkApi) => {
    const { auth, follows } = thunkApi.getState();
    if (auth.token === null) {
      throw new Error("not authenticated");
    }
    const wasFollowed = follows.artistIds.includes(artistId);
    if (wasFollowed) {
      await unfollowArtist(auth.token, artistId);
    } else {
      await followArtist(auth.token, artistId);
    }
    void thunkApi.dispatch(fetchFeedPage({ reset: true }));
  },
);

const followsSlice = createSlice({
  name: "follows",
  initialState,
  reducers: {
    followsCleared() {
      return initialState;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(loadFollows.fulfilled, (state, action) => {
        state.artistIds = action.payload;
      })
      .addCase(toggleFollow.pending, (state, action) => {
        const artistId = action.meta.arg;
        state.pendingToggles.push(artistId);
        state.artistIds = state.artistIds.includes(artistId)
          ? state.artistIds.filter((id) => id !== artistId)
          : [...state.artistIds, artistId];
      })
      .addCase(toggleFollow.fulfilled, (state, action) => {
        state.pendingToggles = state.pendingToggles.filter((id) => id !== action.meta.arg);
      })
      .addCase(toggleFollow.rejected, (state, action) => {
        const artistId = action.meta.arg;
        state.pendingToggles = state.pendingToggles.filter((id) => id !== artistId);
        state.artistIds = state.artistIds.includes(artistId)
          ? state.artistIds.filter((id) => id !== artistId)
          : [...state.artistIds, artistId];
      });
  },
});

export const { followsCleared } = followsSlice.actions;
export default followsSlice.reducer;
