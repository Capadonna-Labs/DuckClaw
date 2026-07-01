'use client';

import { useState } from 'react';
import { DocumentReportsPanel } from '@/components/reports/DocumentReportsPanel';
import { HtmlDashboardReportsPanel } from '@/components/reports/HtmlDashboardReportsPanel';

type ReportsTab = 'word' | 'html';

export default function ReportsPageView() {
  const [tab, setTab] = useState<ReportsTab>('word');

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col overflow-hidden bg-slate-950 text-slate-100">
      <div className="flex shrink-0 items-center gap-1 border-b border-slate-800 px-4 py-2">
        <button
          type="button"
          onClick={() => setTab('word')}
          className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
            tab === 'word' ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          Informes Word
        </button>
        <button
          type="button"
          onClick={() => setTab('html')}
          className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
            tab === 'html' ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          Dashboards HTML
        </button>
      </div>
      <div className="min-h-0 flex-1">
        {tab === 'word' ? <DocumentReportsPanel /> : <HtmlDashboardReportsPanel />}
      </div>
    </div>
  );
}
