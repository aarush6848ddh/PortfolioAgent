'use client';

import { formatCurrency } from '@/lib/utils';
import type { LiveHolding } from '@/lib/useLivePrices';

function TapeItem({ h }: { h: LiveHolding }) {
  return (
    <div className="flex items-center gap-2 px-5 py-1.5 whitespace-nowrap">
      <span className="text-[11px] font-semibold text-bb-amber">{h.ticker}</span>
      <span
        key={`${h.ticker}-${h.tick}`}
        className={`text-[11px] text-bb-white px-1 ${
          h.dir === 'up' ? 'flash-up' : h.dir === 'down' ? 'flash-down' : ''
        }`}
      >
        {formatCurrency(h.current_price)}
      </span>
      <span className={`text-[10px] ${h.day_change >= 0 ? 'text-positive' : 'text-negative'}`}>
        {h.day_change >= 0 ? '\u25B2' : '\u25BC'}
        {Math.abs(h.day_change_pct).toFixed(2)}%
      </span>
    </div>
  );
}

/** Continuous scrolling marquee of holdings + live prices. */
export function TickerTape({ holdings }: { holdings: LiveHolding[] }) {
  if (holdings.length === 0) return null;
  // Repeat the set so the 50% translate loop is seamless even with few tickers.
  const repeats = Math.max(2, Math.ceil(12 / holdings.length));
  const half = Array.from({ length: repeats }, () => holdings).flat();
  return (
    <div className="tape-wrap">
      <div className="tape-track">
        {[0, 1].map((copy) => (
          <div key={copy} className="flex" aria-hidden={copy === 1}>
            {half.map((h, i) => (
              <TapeItem key={`${copy}-${i}-${h.ticker}`} h={h} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
