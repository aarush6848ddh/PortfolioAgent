'use client';

import { useEffect, useRef, useState } from 'react';
import { WS_URL, type Holding } from './api';

/** REST holding merged with live WS state. */
export interface LiveHolding extends Holding {
  dir: 'up' | 'down' | null;
  tick: number;
}

export interface LivePrice {
  price: number;
  ts: number;
  dir: 'up' | 'down' | null; // vs previous tick — drives the flash color
  tick: number; // increments per tick — key changes retrigger the CSS flash
}

/** Connects to the API's /ws endpoint and exposes live per-ticker prices.
 *  Off-hours no trades tick, so callers fall back to the REST snapshot. */
export function useLivePrices() {
  const [prices, setPrices] = useState<Record<string, LivePrice>>({});
  const [connected, setConnected] = useState(false);
  const retryMs = useRef(1000);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let timer: ReturnType<typeof setTimeout>;

    const connect = () => {
      ws = new WebSocket(WS_URL);
      ws.onopen = () => {
        setConnected(true);
        retryMs.current = 1000;
      };
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data) as { ticker: string; price: number; ts: number };
          setPrices((prev) => {
            const last = prev[msg.ticker];
            const dir = !last ? null : msg.price > last.price ? 'up' : msg.price < last.price ? 'down' : last.dir;
            return {
              ...prev,
              [msg.ticker]: { price: msg.price, ts: msg.ts, dir, tick: (last?.tick ?? 0) + 1 },
            };
          });
        } catch {
          // ignore malformed frames
        }
      };
      ws.onclose = () => {
        setConnected(false);
        if (!closed) {
          timer = setTimeout(connect, retryMs.current);
          retryMs.current = Math.min(retryMs.current * 2, 30000);
        }
      };
      ws.onerror = () => ws?.close();
    };

    connect();
    return () => {
      closed = true;
      clearTimeout(timer);
      ws?.close();
    };
  }, []);

  return { prices, connected };
}
