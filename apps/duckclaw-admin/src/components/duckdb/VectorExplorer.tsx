'use client';

import { useCallback, useEffect, useState } from 'react';
import { Loader2, Search } from 'lucide-react';
import { adminService, type VectorMemoryHit } from '@/services/adminService';

type Props = {
  vaultPath: string;
};

function distanceBadgeClass(distance: number | null): string {
  if (distance === null) return 'bg-gov-gray-100 text-gov-gray-700 dark:bg-dark-bg dark:text-dark-muted';
  if (distance < 0.3) return 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200';
  return 'bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-100';
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
    <div className="flex min-h-[480px] flex-col gap-4">
      <section className="rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
        <div className="border-b border-gov-gray-100 px-4 py-3 dark:border-dark-border">
          <h2 className="text-sm font-semibold text-gov-gray-900 dark:text-dark-text">Memoria vectorial</h2>
        </div>
        <div className="flex gap-2 p-4">
          <div className="relative flex-1">
            <Search
              className="absolute left-3 top-1/2 -translate-y-1/2 text-gov-gray-400"
              size={16}
            />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void search(query);
              }}
              placeholder="Buscar en semantic_memory…"
              className="w-full rounded-lg border border-gov-gray-200 bg-white py-2 pl-9 pr-3 text-sm dark:border-dark-border dark:bg-dark-bg"
            />
          </div>
          <button
            type="button"
            onClick={() => void search(query)}
            disabled={loading || !vaultPath}
            className="shrink-0 rounded-lg bg-gov-blue-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            Buscar
          </button>
        </div>
      </section>

      {warning && (
        <p className="text-xs text-amber-800 dark:text-amber-200">{warning}</p>
      )}
      {error && (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-400">
          {error}
        </p>
      )}

      {loading && results.length === 0 ? (
        <div className="flex justify-center py-16">
          <Loader2 className="animate-spin text-gov-gray-400" size={36} />
        </div>
      ) : notInitialized ? (
        <section className="rounded-xl border border-gov-gray-200 bg-white p-8 text-center dark:border-dark-border dark:bg-dark-surface">
          <p className="font-semibold text-gov-gray-900 dark:text-dark-text">
            Memoria vectorial no inicializada
          </p>
          <p className="mt-2 text-sm text-gov-gray-500 dark:text-dark-muted">
            Añade contexto vía playground o bootstrap para crear main.semantic_memory.
          </p>
        </section>
      ) : results.length === 0 ? (
        <p className="py-12 text-center text-sm text-gov-gray-500 dark:text-dark-muted">
          Sin resultados ({mode}).
        </p>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {results.map((hit) => (
            <article
              key={hit.id}
              className="flex flex-col gap-3 rounded-xl border border-gov-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface"
            >
              <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-gov-gray-800 dark:text-dark-text">
                {truncate(hit.text)}
              </p>
              <div className="mt-auto flex flex-wrap items-center gap-2">
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${distanceBadgeClass(hit.distance)}`}>
                  {hit.distance !== null
                    ? `Similitud ${hit.distance.toFixed(3)}`
                    : mode === 'recent'
                      ? 'Reciente'
                      : 'Léxico'}
                </span>
              </div>
              <p className="space-y-0.5 font-mono text-[11px] text-gov-gray-500 dark:text-dark-muted">
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
