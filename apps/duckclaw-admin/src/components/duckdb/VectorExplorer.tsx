'use client';

import { useCallback, useEffect, useState } from 'react';
import { Loader2, Search } from 'lucide-react';
import { adminService, type VectorMemoryHit } from '@/services/adminService';

type Props = {
  vaultPath: string;
};

function distanceBadgeClass(distance: number | null): string {
  if (distance === null) return 'bg-slate-700 text-slate-300';
  if (distance < 0.3) return 'bg-emerald-900/60 text-emerald-300 border-emerald-700';
  return 'bg-amber-900/50 text-amber-200 border-amber-700';
}

function truncate(text: string, max = 400): string {
  const t = (text || '').trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max)}…`;
}

export function VectorExplorer({ vaultPath }: Props) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<VectorMemoryHit[]>([]);
  const [mode, setMode] = useState<string>('recent');
  const [warning, setWarning] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [notInitialized, setNotInitialized] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const search = useCallback(
    async (q: string) => {
      if (!vaultPath) return;
      setLoading(true);
      setError(null);
      setNotInitialized(false);
      try {
        const data = await adminService.searchDuckdbVectorMemory({
          query: q,
          limit: 10,
          vault_path: vaultPath,
        });
        setResults(data.results);
        setMode(data.mode);
        setWarning(data.warning ?? null);
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Error en búsqueda';
        if (/inicializada/i.test(msg)) {
          setNotInitialized(true);
          setResults([]);
        } else {
          setError(msg);
        }
      } finally {
        setLoading(false);
      }
    },
    [vaultPath]
  );

  useEffect(() => {
    void search('');
  }, [search]);

  return (
    <div className="flex flex-col gap-4 h-[calc(100vh-220px)] min-h-[420px]">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search
            className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500"
            size={18}
          />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void search(query);
            }}
            placeholder="Buscar en memoria semántica…"
            className="w-full pl-10 pr-3 py-3 rounded-xl bg-slate-950 border border-slate-800 text-slate-100 text-sm"
          />
        </div>
        <button
          type="button"
          onClick={() => void search(query)}
          disabled={loading || !vaultPath}
          className="px-5 py-3 rounded-xl bg-gov-blue-700 text-white text-sm font-bold disabled:opacity-50 shrink-0"
        >
          Buscar en Memoria
        </button>
      </div>

      {warning && (
        <p className="text-xs text-amber-400/90">{warning}</p>
      )}
      {error && (
        <p className="text-sm text-red-400 bg-red-950/40 border border-red-900/50 rounded-xl px-3 py-2">
          {error}
        </p>
      )}

      {loading && results.length === 0 ? (
        <div className="flex justify-center py-16">
          <Loader2 className="animate-spin text-slate-500" size={36} />
        </div>
      ) : notInitialized ? (
        <div className="rounded-xl border border-slate-800 bg-slate-950 p-8 text-center">
          <p className="text-slate-300 font-semibold">La memoria vectorial aún no ha sido inicializada</p>
          <p className="text-slate-500 text-sm mt-2">
            Ejecuta bootstrap o añade contexto con /context en Telegram para crear main.semantic_memory.
          </p>
        </div>
      ) : results.length === 0 ? (
        <p className="text-slate-500 text-sm text-center py-12">Sin resultados ({mode}).</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 overflow-y-auto flex-1 min-h-0 pr-1">
          {results.map((hit) => (
            <article
              key={hit.id}
              className="rounded-xl border border-slate-800 bg-slate-950 p-4 flex flex-col gap-3"
            >
              <p className="text-sm text-slate-200 leading-relaxed whitespace-pre-wrap break-words">
                {truncate(hit.text)}
              </p>
              <div className="mt-auto flex flex-wrap items-center gap-2">
                <span
                  className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full border ${distanceBadgeClass(hit.distance)}`}
                >
                  {hit.distance !== null
                    ? `Similitud: ${hit.distance.toFixed(3)}`
                    : mode === 'recent'
                      ? 'Reciente'
                      : 'Léxico'}
                </span>
              </div>
              <p className="text-[11px] text-slate-400 font-mono space-y-0.5">
                {hit.metadata.source && <span className="block">source: {hit.metadata.source}</span>}
                {hit.metadata.created_at && (
                  <span className="block">created: {hit.metadata.created_at}</span>
                )}
                {hit.metadata.embedding_status && (
                  <span className="block">status: {hit.metadata.embedding_status}</span>
                )}
              </p>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
