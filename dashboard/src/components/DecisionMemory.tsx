import { Header } from './Header';
import { formatCurrency } from '@/lib/utils';
import type { DecisionMemoryEntry } from '@/lib/api';

function timeAgo(dateStr: string) {
  const d = Math.floor((Date.now() - new Date(dateStr).getTime()) / 86400000);
  if (d === 0) return 'TODAY';
  if (d === 1) return '1D AGO';
  return `${d}D AGO`;
}

export function DecisionMemory({ memories }: { memories: DecisionMemoryEntry[] }) {
  return (
    <div className="lg:col-span-5">
      <Header variant="dark">Decision Memory &mdash; Last {memories.length}</Header>
      <div className="divide-y divide-[#1a1a1a] overflow-y-auto">
        {memories.length > 0 ? (
          memories.map((m, i) => (
            <div key={i} className="flex gap-3 px-3 py-2 hover:bg-[#0d0d0d]">
              <div className="shrink-0 w-14">
                <span className="text-[9px] font-semibold text-bb-amber">
                  {timeAgo(m.date)}
                </span>
                <div className="text-[8px] text-bb-gray-dim">{m.run_type}</div>
              </div>
              <span className="text-[11px] text-bb-gray leading-relaxed">
                {m.takeaway}
              </span>
              {m.portfolio_value && (
                <span className="shrink-0 text-[10px] text-bb-white">
                  {formatCurrency(m.portfolio_value)}
                </span>
              )}
            </div>
          ))
        ) : (
          <div className="p-3 text-[10px] text-bb-gray">NO DECISION MEMORY YET</div>
        )}
      </div>
    </div>
  );
}
