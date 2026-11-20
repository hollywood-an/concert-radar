import { useCallback } from "react";

import { type ActivityKind, recordActivity } from "@/lib/api";
import { useAppSelector } from "@/store/hooks";

// Returns a function that reports an action on a show for the signed-in user.
// Signed out, it does nothing.
export function useRecordActivity(): (kind: ActivityKind, eventId: string) => void {
  const token = useAppSelector((state) => state.auth.token);
  return useCallback(
    (kind, eventId) => {
      if (token !== null) {
        recordActivity(token, kind, eventId);
      }
    },
    [token],
  );
}
