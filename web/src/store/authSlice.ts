import { createAsyncThunk, createSlice, PayloadAction } from "@reduxjs/toolkit";

import { devLogin, getMe } from "@/lib/api";
import type { User } from "@/types";

const TOKEN_KEY = "cr_token";
const USER_KEY = "cr_user";

export interface AuthState {
  user: User | null;
  token: string | null;
  status: "idle" | "loading" | "authenticated" | "error";
}

const initialState: AuthState = { user: null, token: null, status: "idle" };

function persist(token: string, user: User): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export const login = createAsyncThunk("auth/login", async (email: string) => {
  const auth = await devLogin(email);
  persist(auth.token, auth.user);
  return auth;
});

// Adopt a session minted elsewhere (the Spotify OAuth callback redirect).
export const adoptToken = createAsyncThunk("auth/adoptToken", async (token: string) => {
  const user = await getMe(token);
  persist(token, user);
  return { token, user };
});

export const loadSession = createAsyncThunk("auth/loadSession", async () => {
  const token = localStorage.getItem(TOKEN_KEY);
  const stored = localStorage.getItem(USER_KEY);
  if (token === null || stored === null) {
    return null;
  }
  return { token, user: JSON.parse(stored) as User };
});

const authSlice = createSlice({
  name: "auth",
  initialState,
  reducers: {
    loggedOut(state) {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
      state.user = null;
      state.token = null;
      state.status = "idle";
    },
    userUpdated(state, action: PayloadAction<User>) {
      state.user = action.payload;
      if (state.token !== null) {
        persist(state.token, action.payload);
      }
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(login.pending, (state) => {
        state.status = "loading";
      })
      .addCase(login.fulfilled, (state, action) => {
        state.token = action.payload.token;
        state.user = action.payload.user;
        state.status = "authenticated";
      })
      .addCase(login.rejected, (state) => {
        state.status = "error";
      })
      .addCase(adoptToken.fulfilled, (state, action) => {
        state.token = action.payload.token;
        state.user = action.payload.user;
        state.status = "authenticated";
      })
      .addCase(loadSession.fulfilled, (state, action) => {
        if (action.payload !== null) {
          state.token = action.payload.token;
          state.user = action.payload.user;
          state.status = "authenticated";
        }
      });
  },
});

export const { loggedOut, userUpdated } = authSlice.actions;
export default authSlice.reducer;
