import { Header } from './Header';
import type { NewsArticle } from '@/lib/api';

export function NewsPanel({ articles }: { articles: NewsArticle[] }) {
  return (
    <div className="border-b border-bb-border">
      <Header variant="orange">{'\u25A0'} Market News</Header>
      <div className="divide-y divide-[#1a1a1a] max-h-64 overflow-y-auto">
        {articles.length === 0 ? (
          <div className="p-3 text-[10px] text-bb-gray">NO RECENT HEADLINES</div>
        ) : (
          articles.map((a, i) => (
            <div key={i} className="flex items-baseline gap-3 px-3 py-1.5 hover:bg-[#0d0d0d]">
              <span className="shrink-0 text-[9px] text-bb-gray-dim tabular-nums w-20">
                {a.datetime.slice(5, 16)}
              </span>
              <span className="shrink-0 text-[10px] font-semibold text-bb-amber w-12">
                {a.ticker}
              </span>
              <span className="text-[11px] text-bb-white leading-snug">
                {a.headline}
                {a.source && (
                  <span className="ml-2 text-[9px] text-bb-gray-dim uppercase">
                    {a.source}
                  </span>
                )}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
