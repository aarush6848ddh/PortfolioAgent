export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatPercent(value: number): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

export function formatNumber(value: number, decimals = 2): string {
  return value.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function formatCompact(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return `$${value.toFixed(2)}`;
}

export function cn(...classes: (string | boolean | undefined | null)[]): string {
  return classes.filter(Boolean).join(' ');
}

export type MarketStatus = 'OPEN' | 'PRE-MKT' | 'AFTER-HRS' | 'CLOSED';

export function getMarketStatus(now: Date): MarketStatus {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    hourCycle: 'h23',
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).formatToParts(now);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? '';
  const weekday = get('weekday');
  if (weekday === 'Sat' || weekday === 'Sun') return 'CLOSED';
  const mins = parseInt(get('hour'), 10) * 60 + parseInt(get('minute'), 10);
  if (mins >= 570 && mins < 960) return 'OPEN'; // 9:30–16:00 ET
  if (mins >= 240 && mins < 570) return 'PRE-MKT'; // 4:00–9:30 ET
  if (mins >= 960 && mins < 1200) return 'AFTER-HRS'; // 16:00–20:00 ET
  return 'CLOSED';
}

export function getChangeColor(value: number): string {
  if (value > 0) return 'text-positive';
  if (value < 0) return 'text-negative';
  return 'text-muted';
}

export function getChangeBg(value: number): string {
  if (value > 0) return 'bg-positive-dim';
  if (value < 0) return 'bg-negative-dim';
  return 'bg-surface';
}
