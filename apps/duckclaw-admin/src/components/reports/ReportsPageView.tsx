'use client';

import { useCallback, useMemo } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { DocumentReportsPanel } from '@/components/reports/DocumentReportsPanel';
import { HtmlDashboardReportsPanel } from '@/components/reports/HtmlDashboardReportsPanel';
import { parseDeliverable, type ReportsTab } from '@/components/reports/reportsPageViewUtils';

export type { ReportsTab } from '@/components/reports/reportsPageViewUtils';

export default function ReportsPageView() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const tab = useMemo(() => parseDeliverable(searchParams.get('deliverable')), [searchParams]);

  const setTab = useCallback(
    (next: ReportsTab) => {
      const params = new URLSearchParams(searchParams.toString());
      if (next === 'html') {
        params.set('deliverable', 'html');
      } else {
        params.delete('deliverable');
      }
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams]
  );

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
