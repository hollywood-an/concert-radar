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

export interface ToggleFollowArgs {
  artistId: string;
  followed: boolean;
}

function setFollowed(state: FollowsState, artistId: string, followed: boolean): void {
  state.artistIds = state.artistIds.filter((id) => id !== artistId);
  if (followed) {
    state.artistIds.push(artistId);
  }
}

// Optimistic toggle per the spec: flip immediately, revert on failure, then re-rank.
// The caller passes the pre-click `followed` state because the pending reducer flips
// artistIds before this payload creator runs, so reading the store here would see the
// already-flipped value and send the opposite request.
export const toggleFollow = createAsyncThunk<void, ToggleFollowArgs, { state: RootState }>(
  "follows/toggle",
  async ({ artistId, followed }, thunkApi) => {
    const { auth } = thunkApi.getState();
    if (auth.token === null) {
      throw new Error("not authenticated");
    }
    if (followed) {
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
        const { artistId, followed } = action.meta.arg;
        state.pendingToggles.push(artistId);
        setFollowed(state, artistId, !followed);
      })
      .addCase(toggleFollow.fulfilled, (state, action) => {
        const { artistId } = action.meta.arg;
        state.pendingToggles = state.pendingToggles.filter((id) => id !== artistId);
      })
      .addCase(toggleFollow.rejected, (state, action) => {
        const { artistId, followed } = action.meta.arg;
        state.pendingToggles = state.pendingToggles.filter((id) => id !== artistId);
        setFollowed(state, artistId, followed);
      });
  },
});

export const { followsCleared } = followsSlice.actions;
export default followsSlice.reducer;
