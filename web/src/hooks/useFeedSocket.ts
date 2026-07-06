"use client";

import { useEffect, useState } from "react";

import { feedSocketUrl } from "@/lib/api";
import { matchReceived } from "@/store/feedSlice";
import { useAppDispatch } from "@/store/hooks";
import type { FeedItem } from "@/types";

// Live feed updates: new matches pushed by the gateway land at the top of the feed.
export function useFeedSocket(token: string | null): boolean {
  const dispatch = useAppDispatch();
  const [live, setLive] = useState(false);

  useEffect(() => {
    if (token === null) {
      return;
    }
    let socket: WebSocket | null = null;
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      socket = new WebSocket(feedSocketUrl(token));
      socket.onopen = () => setLive(true);
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data as string) as {
          type: string;
          item?: FeedItem;
        };
        if (message.type === "match" && message.item !== undefined) {
          dispatch(matchReceived(message.item));
        }
      };
      socket.onclose = () => {
        setLive(false);
        if (!closed) {
          retry = setTimeout(connect, 3000);
        }
      };
    };
    connect();

    return () => {
      closed = true;
      if (retry !== null) {
        clearTimeout(retry);
      }
      socket?.close();
      setLive(false);
    };
  }, [token, dispatch]);

  return live;
}
