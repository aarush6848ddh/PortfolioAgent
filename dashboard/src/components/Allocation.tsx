'use client';

import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';
import { Header } from './Header';
import { formatCurrency } from '@/lib/utils';
import type { Holding } from '@/lib/api';

export const ALLOC_COLORS = ['#3388ff', '#ff8c00', '#4af6c3', '#ff3b3b', '#00d26a', '#cc5500'];

export function Allocation({ holdings }: { holdings: Holding[] }) {
  return (
    <div className="border-t border-bb-border">
      <Header variant="dark">Allocation</Header>
      {holdings.length === 0 ? (
        <div className="text-[10px] text-bb-gray p-3">NO POSITIONS</div>
      ) : (
        <div className="flex items-center gap-2 p-3">
          {/* Donut */}
          <div className="h-28 w-28 shrink-0">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={holdings.map((h) => ({ name: h.ticker, value: h.weight }))}
                  dataKey="value"
                  innerRadius="55%"
                  outerRadius="100%"
                  stroke="#000"
                  strokeWidth={1}
                  isAnimationActive={false}
                >
                  {holdings.map((h, i) => (
                    <Cell key={h.ticker} fill={ALLOC_COLORS[i % ALLOC_COLORS.length]} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          </div>
          {/* Bars */}
          <div className="flex-1 space-y-2">
            {holdings.map((h, i) => (
              <div key={h.ticker}>
                <div className="mb-1 flex items-center justify-between">
                  <span
                    className="text-[11px] font-semibold"
                    style={{ color: ALLOC_COLORS[i % ALLOC_COLORS.length] }}
                  >
                    {h.ticker}
                  </span>
                  <span className="text-[11px] text-bb-white">
                    {h.weight.toFixed(1)}%
                    <span className="ml-2 text-bb-gray">{formatCurrency(h.value)}</span>
                  </span>
                </div>
                <div className="bb-alloc-bar">
                  <div
                    className="bb-alloc-fill"
                    style={{
                      width: `${h.weight}%`,
                      backgroundColor: ALLOC_COLORS[i % ALLOC_COLORS.length],
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
