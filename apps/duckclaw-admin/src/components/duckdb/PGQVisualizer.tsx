'use client';

import dynamic from 'next/dynamic';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, RefreshCw, Sparkles } from 'lucide-react';
import { adminService, type PgqGraphNode } from '@/services/adminService';

const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), { ssr: false });

const GROUP_COLORS: Record<string, string> = {
  USER: '#38bdf8',
  MERCHANT: '#a78bfa',
  CATEGORY: '#f472b6',
  PREFERENCE: '#34d399',
  PLACE: '#fbbf24',
  PRODUCT: '#fb923c',
  REGIMEN: '#f87171',
  ACTIVO: '#60a5fa',
  SHOCK: '#fb923c',
  PERFIL: '#a78bfa',
  OBJETIVO: '#34d399',
  CURRENCY: '#fbbf24',
  INDICATOR: '#c084fc',
  THESIS: '#38bdf8',
  FRAMEWORK: '#94a3b8',
};

type Props = {
  vaultPath: string;
};

function missingPgqTablesWarning(warning: string | null): boolean {
  if (!warning) return false;
  return warning.toLowerCase().includes('no encontradas');
}

export function PGQVisualizer({ vaultPath }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 500 });
  const [graph, setGraph] = useState<{ nodes: PgqGraphNode[]; links: { source: string; target: string; label: string }[] }>({
    nodes: [],
    links: [],
  });
  const [loading, setLoading] = useState(false);
  const [bootstrapping, setBootstrapping] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [htmlToken, setHtmlToken] = useState(0);
  const [htmlAvailable, setHtmlAvailable] = useState(false);
  const [viewMode, setViewMode] = useState<'html' | 'json'>('json');

  const htmlSrc = useMemo(() => {
    if (!vaultPath) return '';
    return adminService.pgqGraphHtmlUrl(vaultPath, htmlToken || Date.now());
  }, [vaultPath, htmlToken]);

  const checkHtmlAvailable = useCallback(async () => {
    if (!vaultPath) {
      setHtmlAvailable(false);
      return false;
    }
    try {
      const res = await fetch(adminService.pgqGraphHtmlUrl(vaultPath, Date.now()), {
        credentials: 'include',
        cache: 'no-store',
      });
      if (!res.ok) {
        setHtmlAvailable(false);
        return false;
      }
      const text = await res.text();
      const usable =
        text.length > 8000 &&
        !text.includes('lib/bindings/utils.js') &&
        (text.includes('addEdge') || text.includes('nodes ='));
      setHtmlAvailable(usable);
      return usable;
    } catch {
      setHtmlAvailable(false);
      return false;
    }
  }, [vaultPath]);

  const load = useCallback(async () => {
    if (!vaultPath) return;
    setLoading(true);
    setError(null);
    setWarning(null);
    try {
      const data = await adminService.getDuckdbPgqGraph(vaultPath);
      setGraph({ nodes: data.nodes, links: data.links });
      setWarning(data.warning ?? null);
      const htmlOk = await checkHtmlAvailable();
      if (data.nodes.length > 0) {
        setViewMode(htmlOk ? 'html' : 'json');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error cargando grafo');
      setGraph({ nodes: [], links: [] });
    } finally {
      setLoading(false);
    }
  }, [vaultPath, checkHtmlAvailable]);

  const bootstrap = useCallback(async () => {
    if (!vaultPath) return;
    setBootstrapping(true);
    setError(null);
    try {
      await adminService.bootstrapDuckdbPgq(vaultPath);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error inicializando grafo PGQ');
    } finally {
      setBootstrapping(false);
    }
  }, [vaultPath, load]);

  const rebuildHtml = useCallback(async () => {
    if (!vaultPath) return;
    setRebuilding(true);
    setError(null);
    try {
      await adminService.rebuildDuckdbPgqGraph(vaultPath);
      setHtmlToken(Date.now());
      const htmlOk = await checkHtmlAvailable();
      setViewMode(htmlOk ? 'html' : 'json');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error generando grafo HTML');
    } finally {
      setRebuilding(false);
    }
  }, [vaultPath, checkHtmlAvailable]);

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
  }, [viewMode, htmlAvailable]);

  const showBootstrapCta = missingPgqTablesWarning(warning);
  const showHtml = viewMode === 'html' && htmlAvailable && htmlSrc;
  const busy = loading || bootstrapping || rebuilding;

  return (
    <div className="flex min-h-[480px] flex-col gap-3">
      <section className="rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gov-gray-100 px-4 py-3 dark:border-dark-border">
          <div>
            <h2 className="text-sm font-semibold text-gov-gray-900 dark:text-dark-text">Grafo PGQ</h2>
            <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
              {graph.nodes.length} nodos · {graph.links.length} enlaces
              {htmlAvailable ? ' · HTML listo' : ' · sin HTML'}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {htmlAvailable && (
              <button
                type="button"
                onClick={() => setViewMode((m) => (m === 'html' ? 'json' : 'html'))}
                disabled={busy || !vaultPath}
                className="inline-flex items-center gap-1 rounded-lg border border-gov-gray-200 px-2.5 py-1.5 text-xs font-semibold dark:border-dark-border disabled:opacity-50"
              >
                {viewMode === 'html' ? 'Vista JSON' : 'Vista HTML'}
              </button>
            )}
            <button
              type="button"
              onClick={() => void rebuildHtml()}
              disabled={busy || !vaultPath}
              className="inline-flex items-center gap-1 rounded-lg border border-gov-gray-200 px-2.5 py-1.5 text-xs font-semibold dark:border-dark-border disabled:opacity-50"
            >
              <Sparkles size={12} className={rebuilding ? 'animate-pulse' : ''} />
              Actualizar grafo
            </button>
            <button
              type="button"
              onClick={() => void load()}
              disabled={busy || !vaultPath}
              className="inline-flex items-center gap-1 rounded-lg border border-gov-gray-200 px-2.5 py-1.5 text-xs font-semibold dark:border-dark-border disabled:opacity-50"
            >
              <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
              Recargar
            </button>
          </div>
        </div>

        {warning && (
          <div className="mx-4 mt-3 flex flex-wrap items-center gap-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-950/30 dark:text-amber-100">
            <span>{warning}</span>
            {showBootstrapCta && (
              <button
                type="button"
                onClick={() => void bootstrap()}
                disabled={bootstrapping || !vaultPath}
                className="inline-flex items-center gap-1 rounded-md bg-amber-600 px-2 py-1 text-[11px] font-semibold text-white hover:bg-amber-700 disabled:opacity-50"
              >
                {bootstrapping ? <Loader2 size={11} className="animate-spin" /> : null}
                Inicializar grafo PGQ
              </button>
            )}
          </div>
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
          {busy && !showHtml ? (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#0f172a]/60">
              <Loader2 className="animate-spin text-slate-400" size={36} />
            </div>
          ) : null}

          {showHtml ? (
            <iframe
              key={htmlSrc}
              title="Grafo PGQ HTML"
              src={htmlSrc}
              className="h-[420px] w-full border-0"
              sandbox="allow-scripts allow-same-origin"
            />
          ) : graph.nodes.length === 0 ? (
            <p className="absolute inset-0 flex items-center justify-center text-sm text-slate-500">
              {showBootstrapCta
                ? 'Inicializa el grafo PGQ para empezar.'
                : 'Sin nodos PGQ. Pulsa Inicializar para copiar macro → memory.'}
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
