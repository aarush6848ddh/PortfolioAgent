'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  getPortfolio,
  getHistory,
  getFearGreed,
  getAnalysis,
  getQuant,
  getQuantMetrics,
  getSparklines,
  getNews,
  type PortfolioResponse,
  type HistoryResponse,
  type FearGreedResponse,
  type AnalysisResponse,
  type QuantResponse,
  type QuantMetrics,
  type SparklinesResponse,
  type NewsResponse,
} from '@/lib/api';
import { useLivePrices, type LiveHolding } from '@/lib/useLivePrices';
import { TopBar } from '@/components/TopBar';
import { TickerTape } from '@/components/TickerTape';
import { MetricsStrip } from '@/components/MetricsStrip';
import { ValueChart } from '@/components/ValueChart';
import { HoldingsTable } from '@/components/HoldingsTable';
import { Allocation } from '@/components/Allocation';
import { FearGreed } from '@/components/FearGreed';
import { QuantStrip } from '@/components/QuantStrip';
import { Reports, WeeklyReport } from '@/components/Reports';
import { DecisionMemory } from '@/components/DecisionMemory';
import { NewsPanel } from '@/components/NewsPanel';
import { Footer } from '@/components/Footer';

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

function ErrorBanner({ error }: { error: string }) {
  return (
    <div className="border border-bb-red/30 bg-bb-red/10 px-4 py-2 text-xs text-bb-red">
      API ERROR: {error} &mdash; showing cached data
    </div>
  );
}

export default function Terminal() {
  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(null);
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [fearGreed, setFearGreed] = useState<FearGreedResponse | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [quant, setQuant] = useState<QuantResponse | null>(null);
  const [quantMetrics, setQuantMetrics] = useState<QuantMetrics | null>(null);
  const [sparklines, setSparklines] = useState<SparklinesResponse | null>(null);
  const [news, setNews] = useState<NewsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [clock, setClock] = useState(new Date());

  const { prices: livePrices, connected: wsConnected } = useLivePrices();

  async function fetchAll() {
    try {
      const [p, h, fg, a, q, qm, sp, n] = await Promise.all([
        getPortfolio(),
        getHistory(),
        getFearGreed(),
        getAnalysis(),
        getQuant(),
        getQuantMetrics(),
        getSparklines(),
        getNews(),
      ]);
      setPortfolio(p);
      setHistory(h);
      setFearGreed(fg);
      setAnalysis(a);
      setQuant(q);
      setQuantMetrics(qm);
      setSparklines(sp);
      setNews(n);
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
    return () => {
      clearInterval(dataInterval);
      clearInterval(clockInterval);
    };
  }, []);

  // Merge live WS prices over the REST snapshot.
  const holdings: LiveHolding[] = useMemo(() => {
    if (!portfolio) return [];
    const merged = portfolio.holdings.map((h) => {
      const live = livePrices[h.ticker];
      if (!live) return { ...h, dir: null, tick: 0 } as LiveHolding;
      const price = live.price;
      const prevClose = h.current_price - h.day_change;
      const value = h.shares * price;
      const pnl = value - h.shares * h.cost_basis;
      const dayChange = prevClose ? price - prevClose : h.day_change;
      return {
        ...h,
        current_price: price,
        value: Math.round(value * 100) / 100,
        pnl: Math.round(pnl * 100) / 100,
        pnl_pct: h.cost_basis ? Math.round((pnl / (h.shares * h.cost_basis)) * 10000) / 100 : 0,
        day_change: Math.round(dayChange * 100) / 100,
        day_change_pct: prevClose ? Math.round((dayChange / prevClose) * 10000) / 100 : h.day_change_pct,
        dir: live.dir,
        tick: live.tick,
      };
    });
    const totalValue = merged.reduce((sum, h) => sum + h.value, 0);
    return merged.map((h) => ({
      ...h,
      weight: totalValue ? Math.round((h.value / totalValue) * 10000) / 100 : 0,
    }));
  }, [portfolio, livePrices]);

  const summary = useMemo(() => {
    if (!portfolio) return null;
    const s = portfolio.summary;
    const totalValue = holdings.reduce((sum, h) => sum + h.value, 0);
    const totalPnl = totalValue - s.total_cost;
    const dayChange = holdings.reduce((sum, h) => sum + h.day_change * h.shares, 0);
    return {
      ...s,
      total_value: Math.round(totalValue * 100) / 100,
      total_pnl: Math.round(totalPnl * 100) / 100,
      total_pnl_pct: s.total_cost ? Math.round((totalPnl / s.total_cost) * 10000) / 100 : 0,
      day_change: Math.round(dayChange * 100) / 100,
      day_change_pct: totalValue ? Math.round((dayChange / totalValue) * 10000) / 100 : 0,
    };
  }, [portfolio, holdings]);

  if (loading) return <Loading />;
  if (!portfolio || !summary) return <ErrorBanner error={error || 'No data'} />;

  return (
    <div className="flex min-h-screen flex-col bg-bb-black fade-in">
      {error && <ErrorBanner error={error} />}

      <TopBar clock={clock} wsConnected={wsConnected} />
      <TickerTape holdings={holdings} />
      <MetricsStrip summary={summary} positions={holdings.length} fearGreed={fearGreed} />

      {/* Main grid: chart left, holdings/allocation right */}
      <div className="grid grid-cols-1 lg:grid-cols-12 border-b border-bb-border">
        <div className="lg:col-span-7 lg:border-r border-b lg:border-b-0 border-bb-border flex flex-col">
          <ValueChart snapshots={history?.snapshots || []} />
        </div>
        <div className="lg:col-span-5 flex flex-col">
          <HoldingsTable holdings={holdings} sparklines={sparklines?.sparklines || {}} />
          <Allocation holdings={holdings} />
          <FearGreed fg={fearGreed} />
        </div>
      </div>

      <QuantStrip metrics={quantMetrics} />
      <NewsPanel articles={news?.articles || []} />
      <Reports
        morning={analysis?.morning_report || null}
        latest={analysis?.latest_report || null}
      />

      <div className="grid grid-cols-1 lg:grid-cols-12 border-b border-bb-border flex-1">
        <WeeklyReport weekly={quant?.weekly_report || null} />
        <DecisionMemory memories={analysis?.decision_memory || []} />
      </div>

      <Footer />
    </div>
  );
}
