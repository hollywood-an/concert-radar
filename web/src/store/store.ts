import { configureStore } from "@reduxjs/toolkit";

import authReducer from "@/store/authSlice";
import feedReducer from "@/store/feedSlice";
import followsReducer from "@/store/followsSlice";
import mapReducer from "@/store/mapSlice";
import notificationsReducer from "@/store/notificationsSlice";

export const store = configureStore({
  reducer: {
    auth: authReducer,
    feed: feedReducer,
    follows: followsReducer,
    map: mapReducer,
    notifications: notificationsReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
