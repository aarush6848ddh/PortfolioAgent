'use client';

import { AreaChart, Area, XAxis, YAxis, ResponsiveContainer } from 'recharts';
import { Header } from './Header';
import type { FearGreedResponse } from '@/lib/api';

export function FearGreed({ fg }: { fg: FearGreedResponse | null }) {
  if (!fg) return null;
  return (
    <div className="border-t border-bb-border">
      <Header variant="dark">Fear &amp; Greed History</Header>
      {fg.history.length >= 3 ? (
        <div className="p-2 h-20">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={fg.history}>
              <Area
                type="monotone"
                dataKey="value"
                stroke="#ff8c00"
                strokeWidth={1}
                fill="#ff8c0015"
                dot={false}
              />
              <YAxis domain={['dataMin - 5', 'dataMax + 5']} hide />
              <XAxis dataKey="date" hide />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="px-3 py-2">
          {fg.history.map((h) => (
            <div key={h.date} className="flex justify-between text-[10px] py-0.5">
              <span className="text-bb-gray">{h.date.slice(5)}</span>
              <span
                className={
                  h.value <= 40
                    ? 'text-negative'
                    : h.value <= 60
                      ? 'text-bb-amber'
                      : 'text-positive'
                }
              >
                {h.value}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
