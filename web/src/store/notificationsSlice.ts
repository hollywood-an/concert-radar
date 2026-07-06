import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";

import { patchMe } from "@/lib/api";
import { userUpdated } from "@/store/authSlice";
import type { RootState } from "@/store/store";
import type { User } from "@/types";

export interface NotificationPrefs {
  email: boolean;
  quietHoursStart: string | null;
  quietHoursEnd: string | null;
}

export interface NotificationsState {
  prefs: NotificationPrefs;
}

const initialState: NotificationsState = {
  prefs: { email: true, quietHoursStart: null, quietHoursEnd: null },
};

export const savePrefs = createAsyncThunk<User, NotificationPrefs, { state: RootState }>(
  "notifications/savePrefs",
  async (prefs, thunkApi) => {
    const { auth } = thunkApi.getState();
    if (auth.token === null) {
      throw new Error("not authenticated");
    }
    const user = await patchMe(auth.token, {
      alert_email: prefs.email,
      quiet_hours_start: prefs.quietHoursStart,
      quiet_hours_end: prefs.quietHoursEnd,
    });
    thunkApi.dispatch(userUpdated(user));
    return user;
  },
);

function prefsFromUser(user: User): NotificationPrefs {
  return {
    email: user.alert_email,
    quietHoursStart: user.quiet_hours_start,
    quietHoursEnd: user.quiet_hours_end,
  };
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
