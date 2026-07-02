import { formatPercent } from '@/lib/utils';
import type { QuantMetrics } from '@/lib/api';

export function QuantStrip({ metrics }: { metrics: QuantMetrics | null }) {
  if (!metrics || !metrics.correlation_matrix?.tickers?.length) return null;

  const cells = [
    {
      label: 'Sharpe',
      value: metrics.sharpe_ratio.toFixed(2),
      sub: metrics.sharpe_ratio >= 1 ? 'GOOD' : 'LOW',
      subColor: metrics.sharpe_ratio >= 1 ? 'text-positive' : 'text-negative',
    },
    {
      label: 'Sortino',
      value: metrics.sortino_ratio.toFixed(2),
      sub: metrics.sortino_ratio >= 1.5 ? 'STRONG' : 'MODERATE',
      subColor: metrics.sortino_ratio >= 1.5 ? 'text-positive' : 'text-bb-amber',
    },
    {
      label: 'Beta',
      value: metrics.beta.toFixed(2),
      sub: 'VS SPY',
      subColor: 'text-bb-gray',
    },
    {
      label: 'Max Drawdown',
      value: `${metrics.max_drawdown.toFixed(1)}%`,
      sub: metrics.recovery_days != null ? `${metrics.recovery_days}D RECOVERY` : 'OPEN',
      subColor: 'text-negative',
    },
    {
      label: 'Ann. Return',
      value: formatPercent(metrics.annualized_return),
      sub: '252D',
      subColor: metrics.annualized_return >= 0 ? 'text-positive' : 'text-negative',
    },
    {
      label: 'Ann. Vol',
      value: `${metrics.annualized_volatility.toFixed(1)}%`,
      sub: 'STD DEV',
      subColor: 'text-bb-amber',
    },
  ];

  return (
    <div className="border-b border-bb-border">
      <div className="flex flex-wrap">
        {cells.map((m) => (
          <div key={m.label} className="bb-metric flex-1 min-w-[120px]">
            <div className="bb-metric-label">{m.label}</div>
            <div className="bb-metric-value">{m.value}</div>
            <div className={`bb-metric-sub ${m.subColor}`}>{m.sub}</div>
          </div>
        ))}
        {/* Inline correlation matrix */}
        <div className="border-l border-bb-border px-5 py-2 flex flex-col justify-center">
          <div className="bb-metric-label mb-2">Correlation</div>
          <table className="text-center">
            <thead>
              <tr>
                <th className="px-2 py-1 text-[10px] text-bb-gray" />
                {metrics.correlation_matrix.tickers.map((t) => (
                  <th key={t} className="px-4 py-1 text-[10px] text-bb-amber">{t}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {metrics.correlation_matrix.tickers.map((t, i) => (
                <tr key={t}>
                  <td className="pr-2 py-1 text-[10px] text-bb-amber text-left">{t}</td>
                  {metrics.correlation_matrix.matrix[i].map((v, j) => {
                    const bg =
                      i === j
                        ? '#1a1a1a'
                        : v >= 0
                          ? `rgba(0,210,106,${Math.abs(v) * 0.3})`
                          : `rgba(255,59,59,${Math.abs(v) * 0.3})`;
                    return (
                      <td
                        key={j}
                        className="px-4 py-1.5 text-[12px] font-semibold text-bb-white"
                        style={{ backgroundColor: bg }}
                      >
                        {v.toFixed(2)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
