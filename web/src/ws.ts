import { useEffect, useRef, useState } from "react";
import type { ClientMsg, ServerMsg } from "./types";

/**
 * One socket, reconnect forever. That is the whole transport layer.
 *
 * `query` carries the call mode (`?mode=talk`) so the server knows, before the
 * first message, whether the page will send capture frames. `sendBytes` writes
 * a binary frame — talk mode's 1024-byte PCM — which `send` cannot do.
 */
export function useSocket(onMsg: (m: ServerMsg) => void, query = "") {
  const [connected, setConnected] = useState(false);
  const ref = useRef<WebSocket | null>(null);
  const cb = useRef(onMsg);
  cb.current = onMsg;

  useEffect(() => {
    let alive = true;
    let retry = 0;

    const connect = () => {
      if (!alive) return;
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws${query}`);
      ref.current = ws;

      ws.onopen = () => {
        setConnected(true);
        retry = 0;
      };
      ws.onmessage = (ev) => {
        if (typeof ev.data !== "string") return;
        try {
          cb.current(JSON.parse(ev.data) as ServerMsg);
        } catch {
          /* ignore malformed frame */
        }
      };
      ws.onclose = () => {
        setConnected(false);
        if (!alive) return;
        retry = Math.min(retry + 1, 6);
        setTimeout(connect, 400 * retry);
      };
      ws.onerror = () => ws.close();
    };

    connect();
    return () => {
      alive = false;
      ref.current?.close();
    };
  }, [query]);

  const send = (m: ClientMsg) => {
    const ws = ref.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(m));
  };

  const sendBytes = (data: ArrayBuffer) => {
    const ws = ref.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(data);
  };

  return { connected, send, sendBytes };
}

