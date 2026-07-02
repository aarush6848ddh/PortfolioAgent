import { formatCurrency, formatPercent } from '@/lib/utils';
import type { PortfolioSummary, FearGreedResponse } from '@/lib/api';

export function MetricsStrip({
  summary: s,
  positions,
  fearGreed: fg,
}: {
  summary: PortfolioSummary;
  positions: number;
  fearGreed: FearGreedResponse | null;
}) {
  const metrics = [
    {
      label: 'Total Value',
      value: formatCurrency(s.total_value),
      sub: `${formatPercent(s.day_change_pct)} today`,
      subColor: s.day_change >= 0 ? 'text-positive' : 'text-negative',
    },
    {
      label: 'Total P&L',
      value: formatCurrency(s.total_pnl),
      sub: formatPercent(s.total_pnl_pct),
      subColor: s.total_pnl >= 0 ? 'text-positive' : 'text-negative',
    },
    {
      label: 'Day Change',
      value: formatCurrency(s.day_change),
      sub: formatPercent(s.day_change_pct),
      subColor: s.day_change >= 0 ? 'text-positive' : 'text-negative',
    },
    {
      label: 'Cost Basis',
      value: formatCurrency(s.total_cost),
      sub: `${positions} positions`,
      subColor: 'text-bb-gray',
    },
    {
      label: 'Fear & Greed',
      value: fg ? String(fg.value) : '--',
      sub: fg?.label || '--',
      subColor: fg
        ? fg.value <= 40
          ? 'text-negative'
          : fg.value <= 60
            ? 'text-bb-amber'
            : 'text-positive'
        : 'text-bb-gray',
    },
  ];

  return (
    <div className="flex flex-wrap border-b border-bb-border">
      {metrics.map((m) => (
        <div key={m.label} className="bb-metric flex-1 min-w-[120px]">
          <div className="bb-metric-label">{m.label}</div>
          <div className="bb-metric-value">{m.value}</div>
          <div className={`bb-metric-sub ${m.subColor}`}>{m.sub}</div>
        </div>
      ))}
    </div>
  );
}
