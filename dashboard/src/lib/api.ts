const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://aarush-box:8000';

async function fetchAPI<T>(endpoint: string): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`API ${endpoint}: ${res.status}`);
  return res.json();
}

// --- Types matching real API responses ---

export interface Holding {
  ticker: string;
  shares: number;
  cost_basis: number;
  current_price: number;
  value: number;
  pnl: number;
  pnl_pct: number;
  day_change: number;
  day_change_pct: number;
  weight: number;
}

export interface PortfolioSummary {
  total_value: number;
  total_cost: number;
  total_pnl: number;
  total_pnl_pct: number;
  day_change: number;
  day_change_pct: number;
}

export interface PortfolioResponse {
  holdings: Holding[];
  summary: PortfolioSummary;
}

export interface Snapshot {
  date: string;
  total_value: number;
  daily_pnl: number;
  cumulative_pnl: number;
}

export interface HistoryResponse {
  snapshots: Snapshot[];
}

export interface FearGreedResponse {
  value: number;
  label: string;
  history: { date: string; value: number }[];
}

export interface AgentReport {
  run_type: string;
  response: string;
  created_at: string;
}

export interface DecisionMemoryEntry {
  date: string;
  run_type: string;
  takeaway: string;
  portfolio_value: number | null;
}

export interface AnalysisResponse {
  latest_report: AgentReport | null;
  morning_report: AgentReport | null;
  decision_memory: DecisionMemoryEntry[];
}

export interface QuantResponse {
  weekly_report: AgentReport | null;
  morning_report: AgentReport | null;
}

export interface QuantMetrics {
  sharpe_ratio: number;
  sortino_ratio: number;
  beta: number;
  max_drawdown: number;
  max_drawdown_date: string | null;
  recovery_days: number | null;
  annualized_return: number;
  annualized_volatility: number;
  correlation_matrix: {
    tickers: string[];
    matrix: number[][];
  };
}

// --- API calls ---

export function getPortfolio() {
  return fetchAPI<PortfolioResponse>('/portfolio');
}

export function getHistory() {
  return fetchAPI<HistoryResponse>('/portfolio/history?limit=90');
}

export function getFearGreed() {
  return fetchAPI<FearGreedResponse>('/fear-greed');
}

export function getAnalysis() {
  return fetchAPI<AnalysisResponse>('/portfolio/analysis');
}

export function getQuant() {
  return fetchAPI<QuantResponse>('/portfolio/quant');
}

export function getQuantMetrics() {
  return fetchAPI<QuantMetrics>('/portfolio/quant-metrics');
}
