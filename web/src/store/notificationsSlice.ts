import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";

import { patchMe } from "@/lib/api";
import { userUpdated } from "@/store/authSlice";
import type { RootState } from "@/store/store";
import type { User } from "@/types";

export interface NotificationPrefs {
  email: boolean;
}

export interface NotificationsState {
  prefs: NotificationPrefs;
}

const initialState: NotificationsState = {
  prefs: { email: true },
};

export const savePrefs = createAsyncThunk<User, NotificationPrefs, { state: RootState }>(
  "notifications/savePrefs",
  async (prefs, thunkApi) => {
    const { auth } = thunkApi.getState();
    if (auth.token === null) {
      throw new Error("not authenticated");
    }
    const user = await patchMe(auth.token, { alert_email: prefs.email });
    thunkApi.dispatch(userUpdated(user));
    return user;
  },
);

function prefsFromUser(user: User): NotificationPrefs {
  return { email: user.alert_email };
}

const notificationsSlice = createSlice({
  name: "notifications",
  initialState,
  reducers: {
    prefsLoaded(state, action: { payload: User }) {
      state.prefs = prefsFromUser(action.payload);
    },
  },
  extraReducers: (builder) => {
    builder.addCase(savePrefs.fulfilled, (state, action) => {
      state.prefs = prefsFromUser(action.payload);
    });
  },
});

export const { prefsLoaded } = notificationsSlice.actions;
export default notificationsSlice.reducer;
