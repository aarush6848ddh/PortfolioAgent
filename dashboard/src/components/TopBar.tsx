'use client';

import { getMarketStatus, type MarketStatus } from '@/lib/utils';

const STATUS_STYLE: Record<MarketStatus, string> = {
  OPEN: 'text-bb-green border-bb-green/50',
  'PRE-MKT': 'text-bb-amber border-bb-amber/50',
  'AFTER-HRS': 'text-bb-amber border-bb-amber/50',
  CLOSED: 'text-bb-gray border-bb-border',
};

export function TopBar({ clock, wsConnected }: { clock: Date; wsConnected: boolean }) {
  const status = getMarketStatus(clock);
  return (
    <div className="flex flex-wrap items-center justify-between border-b border-bb-border bg-bb-panel">
      <div className="flex items-center gap-2 border-r border-bb-border px-4 py-2">
        <div className="h-3 w-3 bg-bb-amber" />
        <span className="text-sm font-bold text-bb-amber tracking-wider">
          PORTFOLIOAGENT
        </span>
      </div>
      <div className="flex items-center gap-4 border-l border-bb-border px-4 py-2">
        <span className={`border px-2 py-0.5 text-[9px] font-semibold tracking-widest ${STATUS_STYLE[status]}`}>
          {status}
        </span>
        <span className="text-[10px] text-bb-gray tabular-nums">
          {clock.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
          })}
        </span>
        <span className="flex items-center gap-1.5">
          <span className={`h-1.5 w-1.5 blink ${wsConnected ? 'bg-bb-green' : 'bg-bb-amber'}`} />
          <span className={`text-[10px] ${wsConnected ? 'text-bb-green' : 'text-bb-amber'}`}>
            {wsConnected ? 'LIVE' : 'DELAYED'}
          </span>
        </span>
      </div>
    </div>
  );
}
