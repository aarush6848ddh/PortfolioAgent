'use client';

import { Header } from './Header';
import { formatCurrency, formatPercent } from '@/lib/utils';
import type { SparklinePoint } from '@/lib/api';
import type { LiveHolding } from '@/lib/useLivePrices';

/** Inline 30-day mini line — plain SVG keeps N-per-row rendering cheap. */
function Sparkline({ points }: { points: SparklinePoint[] }) {
  if (!points || points.length < 2) return <span className="text-bb-gray-dim">--</span>;
  const values = points.map((p) => p.close);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const w = 64;
  const h = 18;
  const path = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = h - ((v - min) / range) * (h - 2) - 1;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  const up = values[values.length - 1] >= values[0];
  return (
    <svg width={w} height={h} className="inline-block align-middle">
      <path d={path} fill="none" stroke={up ? '#00d26a' : '#ff3b3b'} strokeWidth={1} />
    </svg>
  );
}

export function HoldingsTable({
  holdings,
  sparklines,
}: {
  holdings: LiveHolding[];
  sparklines: Record<string, SparklinePoint[]>;
}) {
  return (
    <div className="flex-1">
      <Header>Holdings</Header>
      <div className="overflow-x-auto">
        <table className="bb-table w-full">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Shrs</th>
              <th>Basis</th>
              <th>Last</th>
              <th>30D</th>
              <th>Mkt Val</th>
              <th>P&L</th>
              <th>P&L%</th>
              <th>Chg</th>
            </tr>
          </thead>
          <tbody>
            {holdings.length === 0 ? (
              <tr>
                <td colSpan={9} className="text-center text-bb-gray py-4">
                  No positions — portfolio is empty
                </td>
              </tr>
            ) : (
              holdings.map((h) => (
                <tr key={h.ticker}>
                  <td className="!text-left font-semibold text-bb-amber">{h.ticker}</td>
                  <td>{h.shares}</td>
                  <td className="text-bb-gray">{h.cost_basis.toFixed(2)}</td>
                  <td
                    key={`last-${h.tick}`}
                    className={`text-bb-white font-semibold ${
                      h.dir === 'up' ? 'flash-up' : h.dir === 'down' ? 'flash-down' : ''
                    }`}
                  >
                    {h.current_price.toFixed(2)}
                  </td>
                  <td>
                    <Sparkline points={sparklines[h.ticker]} />
                  </td>
                  <td className="text-bb-white">{formatCurrency(h.value)}</td>
                  <td className={h.pnl >= 0 ? 'text-positive' : 'text-negative'}>
                    {h.pnl >= 0 ? '+' : ''}
                    {h.pnl.toFixed(2)}
                  </td>
                  <td className={h.pnl_pct >= 0 ? 'text-positive' : 'text-negative'}>
                    {formatPercent(h.pnl_pct)}
                  </td>
                  <td className={h.day_change >= 0 ? 'text-positive' : 'text-negative'}>
                    {h.day_change >= 0 ? '\u25B2' : '\u25BC'}
                    {Math.abs(h.day_change_pct).toFixed(2)}%
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
