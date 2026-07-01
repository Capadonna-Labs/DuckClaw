'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { AdminHubShell } from '@/components/admin/AdminHubShell';
import ReportsPageView from '@/components/reports/ReportsPageView';
import KanbanBoardView from '@/components/kanban/KanbanBoardView';

const TABS = [
  { id: 'reportes', label: 'Reportes', hint: 'Informes Word y dashboards HTML' },
  { id: 'tablero', label: 'Tablero', hint: 'Kanban de tareas y swarm' },
] as const;

type ProductividadTab = (typeof TABS)[number]['id'];

function parseTab(raw: string | null): ProductividadTab {
  if (raw === 'tablero' || raw === 'reportes') return raw;
  return 'reportes';
}

function ProductividadHubContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [tab, setTab] = useState<ProductividadTab>(() => parseTab(searchParams.get('tab')));

  useEffect(() => {
    setTab(parseTab(searchParams.get('tab')));
  }, [searchParams]);

  const selectTab = (next: ProductividadTab) => {
    setTab(next);
    router.replace(`/productividad?tab=${next}`, { scroll: false });
  };

  return (
    <AdminHubShell
      title="Productividad"
      description="Informes y tablero de trabajo del equipo."
      tabs={TABS}
      activeTabId={tab}
      onSelectTab={(id) => selectTab(parseTab(id))}
    >
      {tab === 'reportes' ? <ReportsPageView /> : <KanbanBoardView embedded />}
    </AdminHubShell>
  );
}

export default function ProductividadHubPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[40vh] items-center justify-center">
          <Loader2 className="animate-spin text-gov-blue-700" size={32} />
        </div>
      }
    >
      <ProductividadHubContent />
    </Suspense>
  );
}
