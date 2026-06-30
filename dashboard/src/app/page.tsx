'use client';

import { useEffect, useState } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import {
  getPortfolio,
  getHistory,
  getFearGreed,
  getAnalysis,
  getQuant,
  getQuantMetrics,
  type PortfolioResponse,
  type HistoryResponse,
  type FearGreedResponse,
  type AnalysisResponse,
  type QuantResponse,
  type QuantMetrics,
} from '@/lib/api';
import { formatCurrency, formatPercent } from '@/lib/utils';

// ─── Tooltip ────────────────────────────────────────────────────────
function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value: number; name: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="border border-bb-border bg-bb-panel px-3 py-2">
      <div className="text-[10px] text-bb-gray">{label}</div>
      {payload.map((p) => (
        <div key={p.name} className="text-xs font-semibold text-bb-white">
          {formatCurrency(p.value)}
        </div>
      ))}
    </div>
  );
}

// ─── Section Header ─────────────────────────────────────────────────
function Header({
  children,
  variant = 'blue',
}: {
  children: React.ReactNode;
  variant?: 'blue' | 'orange' | 'dark';
}) {
  const cls =
    variant === 'orange'
      ? 'bb-header bb-header-orange'
      : variant === 'dark'
        ? 'bb-header bb-header-dark'
        : 'bb-header';
  return <div className={cls}>{children}</div>;
}

// ─── Loading Skeleton ───────────────────────────────────────────────
function Loading() {
  return (
    <div className="flex h-screen items-center justify-center bg-bb-black">
      <div className="text-center">
        <div className="text-bb-amber text-sm font-semibold tracking-widest">
          PORTFOLIOAGENT
        </div>
        <div className="text-bb-gray text-[10px] mt-2 blink">
          CONNECTING TO AARUSH-BOX...
        </div>
      </div>
    </div>
  );
}

// ─── Error State ────────────────────────────────────────────────────
function ErrorBanner({ error }: { error: string }) {
  return (
    <div className="border border-bb-red/30 bg-bb-red/10 px-4 py-2 text-xs text-bb-red">
      API ERROR: {error} &mdash; showing cached data
    </div>
  );
}

// ─── Page ───────────────────────────────────────────────────────────
export default function Terminal() {
  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(null);
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [fearGreed, setFearGreed] = useState<FearGreedResponse | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [quant, setQuant] = useState<QuantResponse | null>(null);
  const [quantMetrics, setQuantMetrics] = useState<QuantMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [clock, setClock] = useState(new Date());

  async function fetchAll() {
    try {
      const [p, h, fg, a, q, qm] = await Promise.all([
        getPortfolio(),
        getHistory(),
        getFearGreed(),
        getAnalysis(),
        getQuant(),
        getQuantMetrics(),
      ]);
      setPortfolio(p);
      setHistory(h);
      setFearGreed(fg);
      setAnalysis(a);
      setQuant(q);
      setQuantMetrics(qm);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Connection failed');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchAll();
    const dataInterval = setInterval(fetchAll, 30000);
    const clockInterval = setInterval(() => setClock(new Date()), 1000);
    return () => { clearInterval(dataInterval); clearInterval(clockInterval); };
  }, []);

  if (loading) return <Loading />;
  if (!portfolio) return <ErrorBanner error={error || 'No data'} />;

  const s = portfolio.summary;
  const holdings = portfolio.holdings;
  const snapshots = history?.snapshots || [];
  const fg = fearGreed;
  const latestReport = analysis?.latest_report;
  const morningReport = analysis?.morning_report;
  const memories = analysis?.decision_memory || [];
  const weeklyReport = quant?.weekly_report;

  function timeAgo(dateStr: string) {
    const d = Math.floor(
      (Date.now() - new Date(dateStr).getTime()) / 86400000
    );
    if (d === 0) return 'TODAY';
    if (d === 1) return '1D AGO';
    return `${d}D AGO`;
  }

  function formatTime(iso: string) {
    return new Date(iso).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
    });
  }


  function renderMarkdown(text: string) {
    const parts = text.split(/(\*\*[^*]+\*\*)/g);
    return parts.map((part, i) => {
      const bold = part.match(/^\*\*(.+)\*\*$/);
      if (bold) return <strong key={i} className="text-bb-white font-semibold">{bold[1]}</strong>;
      return <span key={i}>{part}</span>;
    });
  }

  return (
    <div className="flex min-h-screen flex-col bg-bb-black fade-in">
      {error && <ErrorBanner error={error} />}

      {/* ═══ TOP BAR ═══ */}
      <div className="flex flex-wrap items-center border-b border-bb-border bg-bb-panel">
        <div className="flex items-center gap-2 border-r border-bb-border px-4 py-2">
          <div className="h-3 w-3 bg-bb-amber" />
          <span className="text-sm font-bold text-bb-amber tracking-wider">
            PORTFOLIOAGENT
          </span>
        </div>
        <div className="flex flex-1 items-center gap-6 px-4 overflow-x-auto">
          {holdings.map((h) => (
            <div key={h.ticker} className="flex items-center gap-3">
              <span className="font-semibold text-bb-white">{h.ticker}</span>
              <span className="text-bb-white">
                {formatCurrency(h.current_price)}
              </span>
              <span
                className={
                  h.day_change >= 0 ? 'text-positive' : 'text-negative'
                }
              >
                {h.day_change >= 0 ? '\u25B2' : '\u25BC'}
                {Math.abs(h.day_change_pct).toFixed(2)}%
              </span>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-4 border-l border-bb-border px-4 py-2">
          <span className="text-[10px] text-bb-gray tabular-nums">
            {clock.toLocaleTimeString('en-US', {
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
            })}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 bg-bb-green blink" />
            <span className="text-[10px] text-bb-green">LIVE</span>
          </span>
        </div>
      </div>

      {/* ═══ METRICS STRIP ═══ */}
      <div className="flex flex-wrap border-b border-bb-border">
        {[
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
            sub: `${holdings.length} positions`,
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
        ].map((m) => (
          <div key={m.label} className="bb-metric flex-1 min-w-[120px]">
            <div className="bb-metric-label">{m.label}</div>
            <div className="bb-metric-value">{m.value}</div>
            <div className={`bb-metric-sub ${m.subColor}`}>{m.sub}</div>
          </div>
        ))}
      </div>

      {/* ═══ MAIN GRID ═══ */}
      <div className="grid grid-cols-1 lg:grid-cols-12 border-b border-bb-border">
        {/* ─── Portfolio Chart (left 7 cols) ─── */}
        <div className="lg:col-span-7 lg:border-r border-b lg:border-b-0 border-bb-border">
          <Header>
            Portfolio Value &mdash; {snapshots.length}D
          </Header>
          <div className="h-64 p-2">
            {snapshots.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={snapshots}>
                  <defs>
                    <linearGradient id="val-grad" x1="0" y1="0" x2="0" y2="1">
                      <stop
                        offset="0%"
                        stopColor={
                          snapshots[snapshots.length - 1]?.total_value >=
                          snapshots[0]?.total_value
                            ? '#00d26a'
                            : '#ff3b3b'
                        }
                        stopOpacity={0.15}
                      />
                      <stop
                        offset="95%"
                        stopColor="#000"
                        stopOpacity={0}
                      />
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
                    stroke={
                      snapshots[snapshots.length - 1]?.total_value >=
                      snapshots[0]?.total_value
                        ? '#00d26a'
                        : '#ff3b3b'
                    }
                    strokeWidth={1.5}
                    fill="url(#val-grad)"
                    dot={false}
                    name="Value"
                    activeDot={{
                      r: 3,
                      fill: '#00d26a',
                      stroke: '#000',
                      strokeWidth: 1,
                    }}
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

        {/* ─── Holdings + Allocation (right 5 cols) ─── */}
        <div className="lg:col-span-5 flex flex-col">
          <div className="flex-1">
            <Header>Holdings</Header>
            <div className="overflow-x-auto"><table className="bb-table w-full">
              <thead>
                <tr>
                  <th>Ticker</th>
                  <th>Shrs</th>
                  <th>Basis</th>
                  <th>Last</th>
                  <th>Mkt Val</th>
                  <th>P&L</th>
                  <th>P&L%</th>
                  <th>Chg</th>
                </tr>
              </thead>
              <tbody>
                {holdings.map((h) => (
                  <tr key={h.ticker}>
                    <td className="!text-left font-semibold text-bb-amber">
                      {h.ticker}
                    </td>
                    <td>{h.shares}</td>
                    <td className="text-bb-gray">
                      {h.cost_basis.toFixed(2)}
                    </td>
                    <td className="text-bb-white font-semibold">
                      {h.current_price.toFixed(2)}
                    </td>
                    <td className="text-bb-white">
                      {formatCurrency(h.value)}
                    </td>
                    <td
                      className={
                        h.pnl >= 0 ? 'text-positive' : 'text-negative'
                      }
                    >
                      {h.pnl >= 0 ? '+' : ''}
                      {h.pnl.toFixed(2)}
                    </td>
                    <td
                      className={
                        h.pnl_pct >= 0 ? 'text-positive' : 'text-negative'
                      }
                    >
                      {formatPercent(h.pnl_pct)}
                    </td>
                    <td
                      className={
                        h.day_change >= 0
                          ? 'text-positive'
                          : 'text-negative'
                      }
                    >
                      {h.day_change >= 0 ? '\u25B2' : '\u25BC'}
                      {Math.abs(h.day_change_pct).toFixed(2)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          </div>

          {/* Allocation */}
          <div className="border-t border-bb-border">
            <Header variant="dark">Allocation</Header>
            <div className="space-y-2 p-3">
              {holdings.map((h, i) => {
                const colors = [
                  '#3388ff',
                  '#ff8c00',
                  '#4af6c3',
                  '#ff3b3b',
                ];
                return (
                  <div key={h.ticker}>
                    <div className="mb-1 flex items-center justify-between">
                      <span
                        className="text-[11px] font-semibold"
                        style={{ color: colors[i % colors.length] }}
                      >
                        {h.ticker}
                      </span>
                      <span className="text-[11px] text-bb-white">
                        {h.weight.toFixed(1)}%
                        <span className="ml-2 text-bb-gray">
                          {formatCurrency(h.value)}
                        </span>
                      </span>
                    </div>
                    <div className="bb-alloc-bar">
                      <div
                        className="bb-alloc-fill"
                        style={{
                          width: `${h.weight}%`,
                          backgroundColor: colors[i % colors.length],
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* F&G History */}
          {fg && (
            <div className="border-t border-bb-border">
              <Header variant="dark">
                Fear &amp; Greed History
              </Header>
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
                      <span className={h.value <= 40 ? 'text-negative' : h.value <= 60 ? 'text-bb-amber' : 'text-positive'}>
                        {h.value}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ═══ QUANT METRICS ═══ */}
      {quantMetrics && (
        <div className="border-b border-bb-border">
          <div className="flex flex-wrap">
            {[
              {
                label: 'Sharpe',
                value: quantMetrics.sharpe_ratio.toFixed(2),
                sub: quantMetrics.sharpe_ratio >= 1 ? 'GOOD' : 'LOW',
                subColor: quantMetrics.sharpe_ratio >= 1 ? 'text-positive' : 'text-negative',
              },
              {
                label: 'Sortino',
                value: quantMetrics.sortino_ratio.toFixed(2),
                sub: quantMetrics.sortino_ratio >= 1.5 ? 'STRONG' : 'MODERATE',
                subColor: quantMetrics.sortino_ratio >= 1.5 ? 'text-positive' : 'text-bb-amber',
              },
              {
                label: 'Beta',
                value: quantMetrics.beta.toFixed(2),
                sub: 'VS SPY',
                subColor: 'text-bb-gray',
              },
              {
                label: 'Max Drawdown',
                value: `${quantMetrics.max_drawdown.toFixed(1)}%`,
                sub: quantMetrics.recovery_days != null ? `${quantMetrics.recovery_days}D RECOVERY` : 'OPEN',
                subColor: 'text-negative',
              },
              {
                label: 'Ann. Return',
                value: formatPercent(quantMetrics.annualized_return),
                sub: '252D',
                subColor: quantMetrics.annualized_return >= 0 ? 'text-positive' : 'text-negative',
              },
              {
                label: 'Ann. Vol',
                value: `${quantMetrics.annualized_volatility.toFixed(1)}%`,
                sub: 'STD DEV',
                subColor: 'text-bb-amber',
              },
            ].map((m) => (
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
                    {quantMetrics.correlation_matrix.tickers.map((t) => (
                      <th key={t} className="px-4 py-1 text-[10px] text-bb-amber">{t}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {quantMetrics.correlation_matrix.tickers.map((t, i) => (
                    <tr key={t}>
                      <td className="pr-2 py-1 text-[10px] text-bb-amber text-left">{t}</td>
                      {quantMetrics.correlation_matrix.matrix[i].map((v, j) => {
                        const bg = i === j ? '#1a1a1a'
                          : v >= 0 ? `rgba(0,210,106,${Math.abs(v) * 0.3})`
                          : `rgba(255,59,59,${Math.abs(v) * 0.3})`;
                        return (
                          <td key={j} className="px-4 py-1.5 text-[12px] font-semibold text-bb-white" style={{ backgroundColor: bg }}>
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
      )}

      {/* ═══ AGENT REPORTS ═══ */}
      <div className="grid grid-cols-1 lg:grid-cols-12 border-b border-bb-border">
        {/* Morning Report */}
        <div className="lg:col-span-6 lg:border-r border-b lg:border-b-0 border-bb-border">
          <Header>
            {'\u25C6'} Morning Briefing
            {morningReport && (
              <span className="ml-2 text-bb-gray font-normal">
                {formatTime(morningReport.created_at)}
              </span>
            )}
          </Header>
          <div className="p-3 text-[11px] leading-relaxed text-bb-gray max-h-48 overflow-y-auto whitespace-pre-wrap">
            {renderMarkdown(morningReport?.response || 'No morning report yet')}
          </div>
        </div>

        {/* Latest Intraday */}
        <div className="lg:col-span-6">
          <Header variant="orange">
            {'\u25C6'} Latest Update
            {latestReport && (
              <span className="ml-2 font-normal" style={{ color: '#ffaa66' }}>
                {latestReport.run_type.toUpperCase()} &mdash;{' '}
                {formatTime(latestReport.created_at)}
              </span>
            )}
          </Header>
          <div className="p-3 text-[11px] leading-relaxed text-bb-gray max-h-48 overflow-y-auto whitespace-pre-wrap">
            {renderMarkdown(latestReport?.response || 'No reports yet')}
          </div>
        </div>
      </div>

      {/* ═══ WEEKLY + DECISION MEMORY ═══ */}
      <div className="grid grid-cols-1 lg:grid-cols-12 border-b border-bb-border flex-1">
        {/* Weekly Report */}
        <div className="lg:col-span-7 lg:border-r border-b lg:border-b-0 border-bb-border">
          <Header variant="dark">
            {'\u25BA'} Weekly Digest
            {weeklyReport && (
              <span className="ml-2 text-bb-gray font-normal">
                {new Date(weeklyReport.created_at).toLocaleDateString('en-US', {
                  month: 'short',
                  day: 'numeric',
                })}
              </span>
            )}
          </Header>
          <div className="p-3 text-[11px] leading-relaxed text-bb-gray overflow-y-auto whitespace-pre-wrap">
            {renderMarkdown(weeklyReport?.response || 'No weekly report yet')}
          </div>
        </div>

        {/* Decision Memory */}
        <div className="lg:col-span-5">
          <Header variant="dark">
            Decision Memory &mdash; Last {memories.length}
          </Header>
          <div className="divide-y divide-[#1a1a1a] overflow-y-auto">
            {memories.length > 0 ? (
              memories.map((m, i) => (
                <div
                  key={i}
                  className="flex gap-3 px-3 py-2 hover:bg-[#0d0d0d]"
                >
                  <div className="shrink-0 w-14">
                    <span className="text-[9px] font-semibold text-bb-amber">
                      {timeAgo(m.date)}
                    </span>
                    <div className="text-[8px] text-bb-gray-dim">
                      {m.run_type}
                    </div>
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
              <div className="p-3 text-[10px] text-bb-gray">
                NO DECISION MEMORY YET
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ═══ FOOTER ═══ */}
      <div className="flex items-center justify-between border-t border-bb-border px-4 py-1.5">
        <span className="text-[9px] text-bb-gray-dim">
          PORTFOLIOAGENT v1.0 &mdash; GROQ &mdash; DATA VIA FINNHUB
        </span>
        <span className="text-[9px] text-bb-gray-dim">
          POLLING EVERY 30S &mdash; AGENT RUNS EVERY 30M DURING MARKET HOURS
        </span>
      </div>
    </div>
  );
}
