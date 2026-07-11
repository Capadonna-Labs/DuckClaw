'use client';

import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { adminService, type CodeDecisionRow } from '@/services/adminService';

type Props = {
  vaultPath: string;
};

export function CodeDecisionsPanel({ vaultPath }: Props) {
  const [items, setItems] = useState<CodeDecisionRow[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!vaultPath) return;
    setLoading(true);
    setError(null);
    try {
      const res = await adminService.listCodeDecisions(vaultPath, 'PENDING_HITL', 30);
      setItems(res.items || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error cargando decisiones');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [vaultPath]);

  useEffect(() => {
    void load();
  }, [load]);

  const approve = async (id: string) => {
    setBusyId(id);
    setError(null);
    try {
      await adminService.approveCodeDecision({ decision_id: id, vault_path: vaultPath });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al aprobar');
    } finally {
      setBusyId(null);
    }
  };

  const reject = async (id: string) => {
    setBusyId(id);
    setError(null);
    try {
      await adminService.rejectCodeDecision({
        decision_id: id,
        vault_path: vaultPath,
        rationale: 'rejected from admin UI',
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al rechazar');
    } finally {
      setBusyId(null);
    }
  };

  if (!vaultPath) {
    return (
      <p className="text-sm text-gov-gray-500 dark:text-dark-muted">
        Selecciona una bóveda para ver code decisions.
      </p>
    );
  }

  return (
    <section className="rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gov-gray-100 px-4 py-3 dark:border-dark-border">
        <div>
          <h2 className="text-sm font-semibold text-gov-gray-900 dark:text-dark-text">Code HITL</h2>
          <p className="text-xs text-gov-gray-500 dark:text-dark-muted">PENDING_HITL · {items.length} pendientes</p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="inline-flex items-center gap-1 rounded-lg border border-gov-gray-200 px-2.5 py-1.5 text-xs font-semibold dark:border-dark-border"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          Recargar
        </button>
      </div>

      <div className="space-y-3 p-4">
        {error && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-400">
            {error}
          </p>
        )}

        {items.length === 0 ? (
          <p className="text-sm text-gov-gray-500 dark:text-dark-muted">Sin propuestas pendientes.</p>
        ) : (
          <ul className="space-y-3">
            {items.map((row) => (
              <li
                key={row.id}
                className="rounded-lg border border-gov-gray-200 p-3 text-sm dark:border-dark-border"
              >
                <p className="font-semibold text-gov-gray-900 dark:text-dark-text">{row.title}</p>
                <p className="mt-1 font-mono text-xs text-gov-gray-500 dark:text-dark-muted">
                  {row.file_path} · {row.branch_name} · {row.decision_type}
                </p>
                <div className="mt-3 flex gap-2">
                  <button
                    type="button"
                    disabled={busyId === row.id}
                    className="rounded-lg bg-emerald-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                    onClick={() => void approve(row.id)}
                  >
                    Aprobar
                  </button>
                  <button
                    type="button"
                    disabled={busyId === row.id}
                    className="rounded-lg border border-gov-gray-200 px-3 py-1.5 text-xs font-semibold dark:border-dark-border disabled:opacity-50"
                    onClick={() => void reject(row.id)}
                  >
                    Rechazar
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
