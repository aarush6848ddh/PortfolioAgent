'use client';

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { Header, ChartTooltip } from './Header';
import type { Snapshot } from '@/lib/api';

export function ValueChart({ snapshots }: { snapshots: Snapshot[] }) {
  const up =
    snapshots[snapshots.length - 1]?.total_value >= snapshots[0]?.total_value;
  const color = up ? '#00d26a' : '#ff3b3b';

  return (
    <div className="flex flex-1 flex-col">
      <Header>Portfolio Value &mdash; {snapshots.length}D</Header>
      <div className="min-h-64 flex-1 p-2">
        {snapshots.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={snapshots}>
              <defs>
                <linearGradient id="val-grad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#000" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                tickFormatter={(v: string) => v.slice(5)}
                tick={{ fontSize: 9 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tickFormatter={(v: number) =>
                  `$${v >= 1000 ? (v / 1000).toFixed(1) + 'K' : v.toFixed(0)}`
                }
                tick={{ fontSize: 9 }}
                axisLine={false}
                tickLine={false}
                width={48}
                domain={['dataMin - 20', 'dataMax + 20']}
              />
              <Tooltip content={<ChartTooltip />} />
              <Area
                type="monotone"
                dataKey="total_value"
                stroke={color}
                strokeWidth={1.5}
                fill="url(#val-grad)"
                dot={false}
                name="Value"
                activeDot={{ r: 3, fill: color, stroke: '#000', strokeWidth: 1 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center justify-center text-bb-gray text-[10px]">
            NO HISTORY DATA YET
          </div>
        )}
      </div>
    </div>
  );
}
