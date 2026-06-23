'use client';

import { useCallback, useEffect, useState } from 'react';
import { Globe, RefreshCw } from 'lucide-react';
import { adminService } from '@/services/adminService';
import { workerOptionIds } from '@/lib/workerOptions';

type SandboxStatus = Awaited<ReturnType<typeof adminService.getSandboxStatus>>;

type SandboxConfigPanelProps = {
  defaultChatId: string;
  onChatIdChange?: (chatId: string) => void;
  status: SandboxStatus | null;
  onRefresh?: () => void;
};

export function SandboxConfigPanel({
  defaultChatId,
  onChatIdChange,
  status,
  onRefresh,
}: SandboxConfigPanelProps) {
  const [chatId, setChatId] = useState(defaultChatId);
  const [workerId, setWorkerId] = useState('');
  const [workerOptions, setWorkerOptions] = useState<string[]>([]);
  const [containers, setContainers] = useState<
    Awaited<ReturnType<typeof adminService.getSandboxSessions>>['containers']
  >([]);
  const [networkPolicy, setNetworkPolicy] = useState<Awaited<
    ReturnType<typeof adminService.getSandboxChatPolicy>
  > | null>(null);
  const [networkToggling, setNetworkToggling] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const policyChatId = chatId.trim() || defaultChatId;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const sess = await adminService.getSandboxSessions();
      setContainers(sess.containers ?? []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al cargar sesiones');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setChatId((prev) => prev || defaultChatId);
  }, [defaultChatId]);

  useEffect(() => {
    onChatIdChange?.(policyChatId);
  }, [policyChatId, onChatIdChange]);

  useEffect(() => {
    adminService
      .getPlaygroundConfig()
      .then((cfg) => {
        const ids = workerOptionIds(cfg.workers ?? []);
        setWorkerOptions(ids);
        setWorkerId((prev) => prev || ids[0] || '');
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!workerId.trim() || !policyChatId) return;
    adminService
      .getSandboxChatPolicy({ chatId: policyChatId, workerId: workerId.trim() })
      .then(setNetworkPolicy)
      .catch(() => setNetworkPolicy(null));
  }, [workerId, policyChatId]);

  useEffect(() => {
    void load();
  }, [load]);

  const toggleNetwork = async () => {
    if (!workerId.trim() || !networkPolicy?.network_toggle_available) return;
    const nextOn = networkPolicy.effective_network !== 'allow';
    setNetworkToggling(true);
    try {
      await adminService.setSandboxNetwork({
        chatId: policyChatId,
        enabled: nextOn,
        workerId: workerId.trim(),
      });
      const pol = await adminService.getSandboxChatPolicy({
        chatId: policyChatId,
        workerId: workerId.trim(),
      });
      setNetworkPolicy(pol);
      onRefresh?.();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo cambiar la red');
    } finally {
      setNetworkToggling(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
      <section className="rounded-2xl border dark:border-dark-border p-4 space-y-4">
        <h2 className="font-bold text-sm">Política por chat</h2>
        <p className="text-xs text-gov-gray-500">
          El sandbox se asocia al <code className="font-mono">chat_id</code> de la conversación.
          Usa el mismo ID que en Playground para ver sus artefactos.
        </p>
        <label className="block text-xs text-gov-gray-500">
          chat_id
          <input
            value={chatId}
            onChange={(e) => setChatId(e.target.value)}
            className="mt-1 w-full px-2 py-2 text-sm font-mono border rounded-lg dark:border-dark-border dark:bg-dark-surface"
            placeholder="admin-sandbox-workspace"
          />
        </label>
        <label className="block text-xs text-gov-gray-500">
          Worker
          <select
            value={workerId}
            onChange={(e) => setWorkerId(e.target.value)}
            className="mt-1 w-full px-2 py-2 text-sm border rounded-lg dark:border-dark-border dark:bg-dark-surface"
          >
            {workerOptions.map((w) => (
              <option key={w} value={w}>
                {w}
              </option>
            ))}
          </select>
        </label>

        <p className="text-[11px] text-gov-gray-500 rounded-lg bg-gov-gray-50 dark:bg-dark-bg p-2">
          Activa o desactiva el sandbox desde{' '}
          <a href="/playground" className="text-gov-blue-700 font-semibold hover:underline">
            Chat
          </a>{' '}
          con <code className="font-mono">/sandbox on</code> o <code className="font-mono">/sandbox off</code>.
        </p>

        <div className="rounded-xl border dark:border-dark-border p-3 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-bold flex items-center gap-1.5">
              <Globe size={14} /> Internet en sandbox
            </span>
            <button
              type="button"
              role="switch"
              aria-checked={networkPolicy?.effective_network === 'allow'}
              disabled={networkToggling || !networkPolicy?.network_toggle_available}
              onClick={() => void toggleNetwork()}
              className={`relative w-11 h-6 rounded-full transition-colors disabled:opacity-40 ${
                networkPolicy?.effective_network === 'allow'
                  ? 'bg-emerald-600'
                  : 'bg-gov-gray-300 dark:bg-gov-gray-600'
              }`}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
                  networkPolicy?.effective_network === 'allow' ? 'translate-x-5' : ''
                }`}
              />
            </button>
          </div>
          {networkPolicy ? (
            <p className="text-[10px] text-gov-gray-500">
              YAML: {networkPolicy.yaml_network_default} · efectiva:{' '}
              {networkPolicy.effective_network}
            </p>
          ) : null}
        </div>

        {status && !status.ready ? (
          <ul className="text-xs text-amber-700 dark:text-amber-300 list-disc pl-4 space-y-1">
            {(status.hints ?? []).map((h) => (
              <li key={h}>{h}</li>
            ))}
          </ul>
        ) : null}
      </section>

      <section className="rounded-2xl border dark:border-dark-border overflow-hidden">
        <div className="p-3 border-b dark:border-dark-border flex justify-between items-center">
          <h2 className="font-bold text-sm">Contenedores Strix activos</h2>
          <button type="button" onClick={() => void load()} className="text-xs text-sky-600 flex gap-1">
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
            Actualizar
          </button>
        </div>
        {error ? <p className="p-3 text-xs text-red-600">{error}</p> : null}
        <div className="max-h-[400px] overflow-auto">
          <table className="w-full text-xs">
            <thead className="bg-gov-gray-50 dark:bg-dark-bg text-left sticky top-0">
              <tr>
                <th className="px-2 py-2">Sesión</th>
                <th className="px-2 py-2">Tipo</th>
                <th className="px-2 py-2">Estado</th>
                <th className="px-2 py-2">VNC</th>
              </tr>
            </thead>
            <tbody>
              {(containers ?? []).map((c) => (
                <tr key={c.session_id} className="border-t dark:border-dark-border">
                  <td className="px-2 py-2 font-mono truncate max-w-[120px]" title={c.session_id}>
                    {c.session_id}
                  </td>
                  <td className="px-2 py-2">{c.kind}</td>
                  <td className="px-2 py-2">{c.status}</td>
                  <td className="px-2 py-2">
                    {c.novnc_active
                      ? c.seconds_remaining != null
                        ? `${Math.round(c.seconds_remaining)}s`
                        : 'on'
                      : '—'}
                  </td>
                </tr>
              ))}
              {(containers ?? []).length === 0 && (
                <tr>
                  <td colSpan={4} className="px-2 py-8 text-center text-gov-gray-400">
                    Sin contenedores activos
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
