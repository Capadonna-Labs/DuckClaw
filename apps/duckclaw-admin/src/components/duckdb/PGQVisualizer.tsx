'use client';

import dynamic from 'next/dynamic';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2 } from 'lucide-react';
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
    <div className="flex flex-col gap-2 h-[calc(100vh-220px)] min-h-[420px]">
      {warning && (
        <p className="text-xs text-amber-400 bg-amber-950/30 border border-amber-900/40 rounded-xl px-3 py-2">
          {warning}
        </p>
      )}
      {error && (
        <p className="text-sm text-red-400 bg-red-950/40 border border-red-900/50 rounded-xl px-3 py-2">
          {error}
        </p>
      )}
      <div
        ref={containerRef}
        className="flex-1 min-h-0 rounded-xl border border-slate-800 overflow-hidden bg-[#0f172a] relative"
      >
        {loading ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <Loader2 className="animate-spin text-slate-400" size={36} />
          </div>
        ) : graph.nodes.length === 0 ? (
          <p className="absolute inset-0 flex items-center justify-center text-slate-500 text-sm">
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
    </div>
  );
}
