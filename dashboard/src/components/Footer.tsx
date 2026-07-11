const FKEYS: Array<[string, string]> = [
  ['F1', 'OVERVIEW'],
  ['F2', 'NEWS'],
  ['F3', 'HOLDINGS'],
  ['F4', 'ALLOC'],
  ['F8', 'QUANT'],
  ['F9', 'REPORTS'],
  ['F10', 'MEMORY'],
];

export function Footer() {
  return (
    <div className="border-t border-bb-border">
      {/* Command-bar function-key strip (aesthetic terminal chrome) */}
      <div className="flex overflow-x-auto border-b border-bb-border bg-bb-panel">
        {FKEYS.map(([key, label]) => (
          <span key={key} className="fkey">
            <span className="fkey-key">{key}</span>
            <span className="fkey-label">{label}</span>
          </span>
        ))}
      </div>
      <div className="flex items-center justify-between px-4 py-1.5">
        <span className="text-[9px] text-bb-gray-dim">
          PORTFOLIOAGENT v2.0 &mdash; GROQ &mdash; DATA VIA FINNHUB
        </span>
        <span className="text-[9px] text-bb-gray-dim">
          LIVE WS + 30S REST FALLBACK &mdash; AGENT RUNS EVERY 30M DURING MARKET HOURS
        </span>
      </div>
    </div>
  );
}
