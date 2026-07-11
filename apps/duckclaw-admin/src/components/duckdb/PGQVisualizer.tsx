'use client';

import dynamic from 'next/dynamic';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, RefreshCw } from 'lucide-react';
import { adminService, type PgqGraphNode } from '@/services/adminService';

const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), { ssr: false });

const GROUP_COLORS: Record<string, string> = {
  USER: '#38bdf8',
  MERCHANT: '#a78bfa',
  CATEGORY: '#f472b6',
  PREFERENCE: '#34d399',
  PLACE: '#fbbf24',
  PRODUCT: '#fb923c',
};

type Props = {
  vaultPath: string;
};

export function PGQVisualizer({ vaultPath }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 500 });
  const [graph, setGraph] = useState<{ nodes: PgqGraphNode[]; links: { source: string; target: string; label: string }[] }>({
    nodes: [],
    links: [],
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!vaultPath) return;
    setLoading(true);
    setError(null);
    setWarning(null);
    try {
      const data = await adminService.getDuckdbPgqGraph(vaultPath);
      setGraph({ nodes: data.nodes, links: data.links });
      setWarning(data.warning ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error cargando grafo');
      setGraph({ nodes: [], links: [] });
    } finally {
      setLoading(false);
    }
  }, [vaultPath]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      setSize({ w: el.clientWidth, h: el.clientHeight });
    });
    ro.observe(el);
    setSize({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  return (
    <div className="flex min-h-[480px] flex-col gap-3">
      <section className="rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gov-gray-100 px-4 py-3 dark:border-dark-border">
          <div>
            <h2 className="text-sm font-semibold text-gov-gray-900 dark:text-dark-text">Grafo PGQ</h2>
            <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
              {graph.nodes.length} nodos · {graph.links.length} enlaces
            </p>
          </div>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading || !vaultPath}
            className="inline-flex items-center gap-1 rounded-lg border border-gov-gray-200 px-2.5 py-1.5 text-xs font-semibold dark:border-dark-border disabled:opacity-50"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
            Recargar
          </button>
        </div>

        {warning && (
          <p className="mx-4 mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-950/30 dark:text-amber-100">
            {warning}
          </p>
        )}
        {error && (
          <p className="mx-4 mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-400">
            {error}
          </p>
        )}

        <div
          ref={containerRef}
          className="relative m-4 min-h-[420px] overflow-hidden rounded-lg border border-gov-gray-200 bg-[#0f172a] dark:border-dark-border"
        >
          {loading ? (
            <div className="absolute inset-0 flex items-center justify-center">
              <Loader2 className="animate-spin text-slate-400" size={36} />
            </div>
          ) : graph.nodes.length === 0 ? (
            <p className="absolute inset-0 flex items-center justify-center text-sm text-slate-500">
              Sin nodos PGQ en esta bóveda.
            </p>
          ) : (
            <ForceGraph2D
              width={size.w}
              height={size.h}
              graphData={graph}
              nodeLabel={(n) => `${(n as PgqGraphNode).label} (${(n as PgqGraphNode).group})`}
              nodeCanvasObjectMode={() => 'after'}
              nodeColor={(n) => GROUP_COLORS[(n as PgqGraphNode).group] ?? '#64748b'}
              linkLabel={(l) => String((l as { label?: string }).label ?? '')}
              linkColor={() => 'rgba(148, 163, 184, 0.45)'}
              backgroundColor="#0f172a"
            />
          )}
        </div>
      </section>
    </div>
  );
}
