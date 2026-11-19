"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { Provider } from "react-redux";

import { loadSession } from "@/store/authSlice";
import { store } from "@/store/store";

// False until the stored session has been checked. Pages wait for it before choosing
// between the app and the sign-in screen, so a signed-in reload never flashes the form.
const SessionReadyContext = createContext(false);

export function useSessionReady(): boolean {
  return useContext(SessionReadyContext);
}

export default function Providers({ children }: { children: React.ReactNode }) {
  const started = useRef(false);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (!started.current) {
      started.current = true;
      void store.dispatch(loadSession()).finally(() => setReady(true));
    }
  }, []);
  return (
    <Provider store={store}>
      <SessionReadyContext.Provider value={ready}>{children}</SessionReadyContext.Provider>
    </Provider>
  );
}
