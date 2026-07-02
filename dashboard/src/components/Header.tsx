import { formatCurrency } from '@/lib/utils';

// Bloomberg section header bar
export function Header({
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

export function ChartTooltip({
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
