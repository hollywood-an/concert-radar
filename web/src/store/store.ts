import { configureStore } from "@reduxjs/toolkit";

import authReducer from "@/store/authSlice";
import feedReducer from "@/store/feedSlice";
import followsReducer from "@/store/followsSlice";
import mapReducer from "@/store/mapSlice";
import notificationsReducer from "@/store/notificationsSlice";

// Tests build a fresh store per case from the same reducers the app uses.
export function makeStore() {
  return configureStore({
    reducer: {
      auth: authReducer,
      feed: feedReducer,
      follows: followsReducer,
      map: mapReducer,
      notifications: notificationsReducer,
    },
  });
}

export const store = makeStore();

export type AppStore = ReturnType<typeof makeStore>;
export type RootState = ReturnType<AppStore["getState"]>;
export type AppDispatch = AppStore["dispatch"];
