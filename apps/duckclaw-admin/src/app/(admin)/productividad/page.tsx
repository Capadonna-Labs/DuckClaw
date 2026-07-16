'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { AdminHubShell } from '@/components/admin/AdminHubShell';
import { ProductivityArtifactsPanel } from '@/components/productivity/ProductivityArtifactsPanel';
import KanbanBoardView from '@/components/kanban/KanbanBoardView';

const TABS = [
  { id: 'artefactos', label: 'Artefactos', hint: 'Bandeja, vault e informes' },
  { id: 'tablero', label: 'Tablero', hint: 'Kanban de tareas y swarm' },
] as const;

type ProductividadTab = (typeof TABS)[number]['id'];

function parseTab(raw: string | null): ProductividadTab {
  // Compat: reportes vivía como hub; ahora es subvista de Artefactos
  if (raw === 'tablero') return 'tablero';
  return 'artefactos';
}

function ProductividadHubContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [tab, setTab] = useState<ProductividadTab>(() => parseTab(searchParams.get('tab')));

  useEffect(() => {
    const raw = searchParams.get('tab');
    // Legacy deep-link /productividad?tab=reportes → artefactos + view=informes
    if (raw === 'reportes') {
      router.replace('/productividad?tab=artefactos&view=informes', { scroll: false });
      setTab('artefactos');
      return;
    }
    setTab(parseTab(raw));
  }, [searchParams, router]);

  const selectTab = (next: ProductividadTab) => {
    setTab(next);
    if (next === 'tablero') {
      router.replace('/productividad?tab=tablero', { scroll: false });
      return;
    }
    const view = searchParams.get('view');
    const qs = view ? `?tab=artefactos&view=${encodeURIComponent(view)}` : '?tab=artefactos';
    router.replace(`/productividad${qs}`, { scroll: false });
  };

  return (
    <AdminHubShell
      title="Productividad"
      description="Entregables del agente y tablero de trabajo."
      tabs={TABS}
      activeTabId={tab}
      onSelectTab={(id) => selectTab(parseTab(id))}
    >
      {tab === 'artefactos' ? <ProductivityArtifactsPanel /> : <KanbanBoardView embedded />}
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
