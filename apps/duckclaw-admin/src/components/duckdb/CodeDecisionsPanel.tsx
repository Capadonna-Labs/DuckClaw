'use client';

import { useCallback, useEffect, useState } from 'react';
import { adminService, type CodeDecisionRow } from '@/services/adminService';

type Props = {
  vaultPath: string;
};

export function CodeDecisionsPanel({ vaultPath }: Props) {
  const [items, setItems] = useState<CodeDecisionRow[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!vaultPath) return;
    setError(null);
    try {
      const res = await adminService.listCodeDecisions(vaultPath, 'PENDING_HITL', 30);
      setItems(res.items || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error cargando decisiones');
      setItems([]);
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
    return <p className="text-sm text-muted-foreground">Selecciona un vault para ver code decisions.</p>;
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">Code decisions (PENDING_HITL)</h3>
        <button type="button" className="text-xs underline" onClick={() => void load()}>
          Refresh
        </button>
      </div>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">Sin propuestas pendientes.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((row) => (
            <li key={row.id} className="rounded border p-3 text-sm">
              <div className="font-medium">{row.title}</div>
              <div className="text-muted-foreground">
                {row.file_path} · {row.branch_name} · {row.decision_type}
              </div>
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  disabled={busyId === row.id}
                  className="rounded bg-emerald-700 px-2 py-1 text-xs text-white disabled:opacity-50"
                  onClick={() => void approve(row.id)}
                >
                  Approve PR
                </button>
                <button
                  type="button"
                  disabled={busyId === row.id}
                  className="rounded border px-2 py-1 text-xs disabled:opacity-50"
                  onClick={() => void reject(row.id)}
                >
                  Reject
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
