export interface Holding {
  ticker: string;
  name: string;
  shares: number;
  cost_basis: number;
  current_price: number;
  value: number;
  pnl: number;
  pnl_pct: number;
  weight: number;
  day_change: number;
  day_change_pct: number;
}

export interface DailySnapshot {
  date: string;
  total_value: number;
  daily_pnl: number;
  cumulative_pnl: number;
}

export interface FearGreed {
  value: number;
  label: string;
  history: { date: string; value: number }[];
}

export interface AgentAnalysis {
  timestamp: string;
  bull_case: string;
  bear_case: string;
  synthesis: string;
  sentiment_score: number;
  model: string;
}

export interface DecisionMemoryEntry {
  id: number;
  timestamp: string;
  takeaway: string;
}

export interface QuantMetrics {
  sharpe_ratio: number;
  sortino_ratio: number;
  beta: number;
  max_drawdown: number;
  max_drawdown_date: string;
  recovery_days: number | null;
  annualized: boolean;
  annualized_return: number | null;
  period_return: number;
  period_start: string | null;
  period_end: string | null;
  annualized_volatility: number;
  correlation_matrix: {
    tickers: string[];
    matrix: number[][];
  };
  monte_carlo: {
    days: number;
    runs: number;
    percentiles: {
      p5: number[];
      p25: number[];
      p50: number[];
      p75: number[];
      p95: number[];
    };
  };
}

// --- Holdings ---
const soxxValue = 15 * 253.47;
const vtiValue = 25 * 291.83;
const totalValue = soxxValue + vtiValue;

export const mockHoldings: Holding[] = [
  {
    ticker: 'SOXX',
    name: 'iShares Semiconductor ETF',
    shares: 15,
    cost_basis: 215.00,
    current_price: 253.47,
    value: soxxValue,
    pnl: (253.47 - 215.00) * 15,
    pnl_pct: ((253.47 - 215.00) / 215.00) * 100,
    weight: (soxxValue / totalValue) * 100,
    day_change: 3.21,
    day_change_pct: 1.28,
  },
  {
    ticker: 'VTI',
    name: 'Vanguard Total Stock Market ETF',
    shares: 25,
    cost_basis: 265.00,
    current_price: 291.83,
    value: vtiValue,
    pnl: (291.83 - 265.00) * 25,
    pnl_pct: ((291.83 - 265.00) / 265.00) * 100,
    weight: (vtiValue / totalValue) * 100,
    day_change: 1.47,
    day_change_pct: 0.51,
  },
];

export const mockPortfolioSummary = {
  total_value: totalValue,
  total_cost: 215.00 * 15 + 265.00 * 25,
  total_pnl: totalValue - (215.00 * 15 + 265.00 * 25),
  total_pnl_pct: ((totalValue - (215.00 * 15 + 265.00 * 25)) / (215.00 * 15 + 265.00 * 25)) * 100,
  day_change: 3.21 * 15 + 1.47 * 25,
  day_change_pct: ((3.21 * 15 + 1.47 * 25) / totalValue) * 100,
};

// --- Daily Snapshots (30 days) ---
function generateSnapshots(): DailySnapshot[] {
  const snapshots: DailySnapshot[] = [];
  const baseValue = 10200;
  const now = new Date();
  let cumPnl = 0;

  const dailyReturns = [
    0.3, -0.8, 1.2, 0.5, -0.3, 0.9, -1.4, 0.7, 0.2, -0.6,
    1.5, -0.4, 0.8, -1.1, 0.6, 1.3, -0.2, 0.4, -0.9, 1.8,
    -0.5, 0.3, 1.1, -0.7, 0.9, -0.1, 1.4, 0.6, -0.3, 0.8,
  ];

  let value = baseValue;
  for (let i = 29; i >= 0; i--) {
    const date = new Date(now);
    date.setDate(date.getDate() - i);
    const dailyReturn = dailyReturns[29 - i];
    const dailyPnl = value * (dailyReturn / 100);
    value += dailyPnl;
    cumPnl += dailyPnl;

    snapshots.push({
      date: date.toISOString().split('T')[0],
      total_value: Math.round(value * 100) / 100,
      daily_pnl: Math.round(dailyPnl * 100) / 100,
      cumulative_pnl: Math.round(cumPnl * 100) / 100,
    });
  }
  return snapshots;
}

export const mockSnapshots = generateSnapshots();

// --- Fear & Greed ---
function generateFearGreedHistory(): { date: string; value: number }[] {
  const history: { date: string; value: number }[] = [];
  const now = new Date();
  let value = 38;
  for (let i = 29; i >= 0; i--) {
    const date = new Date(now);
    date.setDate(date.getDate() - i);
    value += Math.floor(Math.random() * 11) - 5;
    value = Math.max(10, Math.min(85, value));
    history.push({ date: date.toISOString().split('T')[0], value });
  }
  return history;
}

function getFearGreedLabel(value: number): string {
  if (value <= 20) return 'Extreme Fear';
  if (value <= 40) return 'Fear';
  if (value <= 60) return 'Neutral';
  if (value <= 80) return 'Greed';
  return 'Extreme Greed';
}

const fgHistory = generateFearGreedHistory();
export const mockFearGreed: FearGreed = {
  value: 42,
  label: getFearGreedLabel(42),
  history: fgHistory,
};

// --- Agent Analysis ---
export const mockAnalysis: AgentAnalysis = {
  timestamp: new Date().toISOString(),
  bull_case: `**Semiconductor momentum remains strong.** SOXX is benefiting from the ongoing AI infrastructure buildout — NVIDIA, Broadcom, and AMD all posted beats last quarter. The SOX index is up 18% YTD, outpacing the S&P 500 by 7 percentage points. Foundry capex forecasts from TSMC and Samsung point to sustained demand through 2027.\n\n**Broad market resilience.** VTI tracks the total US market, which continues to grind higher on robust consumer spending and easing inflation (CPI at 2.8%). Employment data remains solid with unemployment at 3.9%. The Fed's dot plot signals one more cut this year, which should support multiples.\n\n**Portfolio positioning is sound.** Your 35/65 SOXX/VTI split gives you concentrated semiconductor upside with a diversified base. If AI capex continues accelerating, SOXX could see another 15-20% from here.`,
  bear_case: `**Valuation risk is real.** SOXX trades at 28x forward earnings — well above the 5-year average of 22x. Any miss on AI revenue expectations (particularly from NVIDIA's data center segment) could trigger a sharp correction. The semiconductor cycle historically mean-reverts hard.\n\n**Macro headwinds building.** While inflation has eased, the 10-year yield at 4.3% creates competition for equities. Consumer credit delinquencies are ticking up (auto loans at 2019 highs). A growth scare could hit both positions simultaneously.\n\n**Concentration risk in SOXX.** Top 3 holdings (NVIDIA, Broadcom, AMD) represent 38% of the ETF. This isn't true diversification — it's a leveraged bet on AI infrastructure spending. If hyperscaler capex disappoints, the drawdown could be 25-30% in weeks.\n\n**Geopolitical tail risk.** Taiwan Strait tensions remain elevated. Any disruption to TSMC operations would be catastrophic for SOXX holdings.`,
  synthesis: `**VERDICT: CAUTIOUSLY BULLISH — Hold current positions.**\n\nThe bull case is stronger on fundamentals — AI infrastructure spending has real revenue behind it (not speculation), and VTI provides a solid diversified floor. However, the bear case correctly identifies elevated valuations as the primary risk.\n\n**Action items:**\n- No trades recommended today\n- Watch NVIDIA earnings next week — this is the bellwether for your SOXX thesis\n- If F&G drops below 25, consider adding to VTI (buy fear)\n- If SOXX hits 30x forward P/E, consider trimming 2-3 shares to lock in gains\n\n**TAKEAWAY:** Semiconductor momentum intact but priced for perfection. Hold, don't chase. VTI position provides downside cushion if AI narrative stumbles.`,
  sentiment_score: 0.65,
  model: 'openai/gpt-oss-120b',
};

// --- Decision Memory ---
export const mockDecisionMemory: DecisionMemoryEntry[] = [
  {
    id: 5,
    timestamp: new Date(Date.now() - 0 * 86400000).toISOString(),
    takeaway: 'Semiconductor momentum intact but priced for perfection. Hold, don\'t chase. VTI position provides downside cushion if AI narrative stumbles.',
  },
  {
    id: 4,
    timestamp: new Date(Date.now() - 1 * 86400000).toISOString(),
    takeaway: 'F&G dropped to 38 — entering fear territory. Historical analysis shows buying VTI below F&G 30 has yielded 12% avg returns over next 6 months. Set mental alert.',
  },
  {
    id: 3,
    timestamp: new Date(Date.now() - 2 * 86400000).toISOString(),
    takeaway: 'SOXX concentration at 34% is within acceptable range. No rebalancing needed. The 35/65 split naturally drifts toward SOXX due to higher volatility — monitor weekly.',
  },
  {
    id: 2,
    timestamp: new Date(Date.now() - 4 * 86400000).toISOString(),
    takeaway: 'Market sold off 2.1% on hot jobs data but recovered by close. Pattern recognition: intraday panic on macro data has been a buying opportunity 7 of last 9 times. Don\'t react to headlines.',
  },
  {
    id: 1,
    timestamp: new Date(Date.now() - 7 * 86400000).toISOString(),
    takeaway: 'Weekly review: portfolio up 1.8% vs S&P +1.2%. SOXX outperformance driven by NVIDIA earnings beat. VTI lagged slightly. Overall allocation working as intended — semiconductors provide alpha, VTI provides stability.',
  },
];

// --- Quant Metrics ---
function generateMonteCarlo(): QuantMetrics['monte_carlo'] {
  const days = 252;
  const startValue = totalValue;
  const p5: number[] = [];
  const p25: number[] = [];
  const p50: number[] = [];
  const p75: number[] = [];
  const p95: number[] = [];

  for (let d = 0; d <= days; d += 5) {
    const t = d / days;
    const drift = startValue * (1 + 0.12 * t);
    const vol = startValue * 0.18 * Math.sqrt(t);

    p5.push(Math.round(drift - 1.645 * vol));
    p25.push(Math.round(drift - 0.675 * vol));
    p50.push(Math.round(drift));
    p75.push(Math.round(drift + 0.675 * vol));
    p95.push(Math.round(drift + 1.645 * vol));
  }

  return { days, runs: 1000, percentiles: { p5, p25, p50, p75, p95 } };
}

export const mockQuantMetrics: QuantMetrics = {
  sharpe_ratio: 1.24,
  sortino_ratio: 1.67,
  beta: 1.15,
  max_drawdown: -8.73,
  max_drawdown_date: '2026-04-12',
  recovery_days: 14,
  annualized: true,
  annualized_return: 14.2,
  period_return: 16.8,
  period_start: '2025-04-12',
  period_end: '2026-04-12',
  annualized_volatility: 11.5,
  correlation_matrix: {
    tickers: ['SOXX', 'VTI', 'SPY'],
    matrix: [
      [1.0, 0.82, 0.79],
      [0.82, 1.0, 0.99],
      [0.79, 0.99, 1.0],
    ],
  },
  monte_carlo: generateMonteCarlo(),
};
