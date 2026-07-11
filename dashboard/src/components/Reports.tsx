import { Header } from './Header';
import { renderMarkdown } from '@/lib/markdown';
import type { AgentReport } from '@/lib/api';

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function Reports({
  morning,
  latest,
}: {
  morning: AgentReport | null;
  latest: AgentReport | null;
}) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 border-b border-bb-border">
      <div className="lg:col-span-6 lg:border-r border-b lg:border-b-0 border-bb-border">
        <Header>
          {'\u25C6'} Morning Briefing
          {morning && (
            <span className="ml-2 text-bb-gray font-normal">
              {formatTime(morning.created_at)}
            </span>
          )}
        </Header>
        <div className="p-3 text-[11px] leading-relaxed text-bb-gray max-h-48 overflow-y-auto">
          {renderMarkdown(morning?.response || 'No morning report yet')}
        </div>
      </div>

      <div className="lg:col-span-6">
        <Header variant="orange">
          {'\u25C6'} Latest Update
          {latest && (
            <span className="ml-2 font-normal" style={{ color: '#ffaa66' }}>
              {latest.run_type.toUpperCase()} &mdash; {formatTime(latest.created_at)}
            </span>
          )}
        </Header>
        <div className="p-3 text-[11px] leading-relaxed text-bb-gray max-h-48 overflow-y-auto">
          {renderMarkdown(latest?.response || 'No reports yet')}
        </div>
      </div>
    </div>
  );
}

export function WeeklyReport({ weekly }: { weekly: AgentReport | null }) {
  return (
    <div className="lg:col-span-7 lg:border-r border-b lg:border-b-0 border-bb-border">
      <Header variant="dark">
        {'\u25BA'} Weekly Digest
        {weekly && (
          <span className="ml-2 text-bb-gray font-normal">
            {new Date(weekly.created_at).toLocaleDateString('en-US', {
              month: 'short',
              day: 'numeric',
            })}
          </span>
        )}
      </Header>
      <div className="p-3 text-[11px] leading-relaxed text-bb-gray overflow-y-auto">
        {renderMarkdown(weekly?.response || 'No weekly report yet')}
      </div>
    </div>
  );
}
