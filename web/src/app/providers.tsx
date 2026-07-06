"use client";

import { useEffect, useRef } from "react";
import { Provider } from "react-redux";

import { loadSession } from "@/store/authSlice";
import { store } from "@/store/store";

export default function Providers({ children }: { children: React.ReactNode }) {
  const hydrated = useRef(false);
  useEffect(() => {
    if (!hydrated.current) {
      hydrated.current = true;
      void store.dispatch(loadSession());
    }
  }, []);
  return <Provider store={store}>{children}</Provider>;
}
