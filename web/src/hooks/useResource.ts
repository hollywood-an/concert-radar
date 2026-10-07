import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";

export type Resource<T> =
  | { status: "loading" }
  | { status: "loaded"; data: T }
  | { status: "not_found" }
  | { status: "error" };

// Runs `load` whenever it changes (memoize it); null means "not ready to load yet".
// 422 counts as not found because the gateway rejects a malformed id before looking it up.
export function useResource<T>(load: (() => Promise<T>) | null): Resource<T> {
  const [resource, setResource] = useState<Resource<T>>({ status: "loading" });

  useEffect(() => {
    if (load === null) {
      return;
    }
    let current = true;
    setResource({ status: "loading" });
    load().then(
      (data) => {
        if (current) {
          setResource({ status: "loaded", data });
        }
      },
      (error: unknown) => {
        if (current) {
          const missing =
            error instanceof ApiError && (error.status === 404 || error.status === 422);
          setResource({ status: missing ? "not_found" : "error" });
        }
      },
    );
    return () => {
      current = false;
    };
  }, [load]);

  return resource;
}
