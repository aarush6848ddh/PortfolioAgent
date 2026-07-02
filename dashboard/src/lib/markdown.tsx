import React from 'react';

function renderInline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    const bold = part.match(/^\*\*(.+)\*\*$/);
    if (bold) return <strong key={i} className="text-bb-white font-semibold">{bold[1]}</strong>;
    return <span key={i}>{part}</span>;
  });
}

/** Renders agent-report markdown: ### headings, bullet lists, **bold**. */
export function renderMarkdown(text: string) {
  const lines = text.split('\n');
  return lines.map((line, i) => {
    const heading = line.match(/^#{1,4}\s+(.+)$/);
    if (heading) {
      return (
        <div key={i} className="text-bb-amber font-semibold uppercase tracking-wider text-[10px] mt-2 mb-1">
          {renderInline(heading[1])}
        </div>
      );
    }
    const bullet = line.match(/^\s*[-*\u2022]\s+(.+)$/);
    if (bullet) {
      return (
        <div key={i} className="flex gap-2 pl-1">
          <span className="text-bb-amber shrink-0">{'\u2023'}</span>
          <span>{renderInline(bullet[1])}</span>
        </div>
      );
    }
    if (line.trim() === '') return <div key={i} className="h-2" />;
    return <div key={i}>{renderInline(line)}</div>;
  });
}
