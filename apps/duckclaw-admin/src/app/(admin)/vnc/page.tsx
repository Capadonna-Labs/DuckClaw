'use client';

import { useCallback, useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';
import { PageShell } from '@/components/admin/PageShell';
import { ExternalLink, Globe, Monitor, RefreshCw } from 'lucide-react';
import { workerOptionId, workerOptionIds } from '@/lib/workerOptions';

/** Mismo chat_id que el chat flotante en /vnc (FloatingAdminChat). */
const POLICY_CHAT_ID = 'admin-section-vnc';

type SandboxContainer = {
  session_id: string;
  container_name: string;
  status: string;
  image: string;
  kind: string;
  novnc_active?: boolean;
  seconds_remaining?: number | null;
  vnc_url?: string | null;
};

export default function VncPage() {
  const [status, setStatus] = useState<Awaited<ReturnType<typeof adminService.getSandboxStatus>> | null>(
    null,
  );
  const [containers, setContainers] = useState<SandboxContainer[]>([]);
  const [chatId, setChatId] = useState('');
  const [workerId, setWorkerId] = useState('');
  const [workerOptions, setWorkerOptions] = useState<string[]>([]);
  const [browserWorkerIds, setBrowserWorkerIds] = useState<Set<string>>(new Set());
  const [vncUrl, setVncUrl] = useState<string | null>(null);
  const [prepareMeta, setPrepareMeta] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [preparing, setPreparing] = useState(false);
  const [networkPolicy, setNetworkPolicy] = useState<Awaited<
    ReturnType<typeof adminService.getSandboxChatPolicy>
  > | null>(null);
  const [networkToggling, setNetworkToggling] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [st, sess] = await Promise.all([
        adminService.getSandboxStatus(),
        adminService.getSandboxSessions(),
      ]);
      setStatus(st);
      setContainers(sess.containers ?? []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al cargar sandbox');
    } finally {
      setLoading(false);
    }
  }, []);

  const policyChatId = (chatId.trim() || POLICY_CHAT_ID).trim();

  const loadNetworkPolicy = useCallback(
    async (wid: string, policyChat: string) => {
      if (!wid.trim() || !policyChat.trim()) {
        setNetworkPolicy(null);
        return;
      }
      try {
        const pol = await adminService.getSandboxChatPolicy({
          chatId: policyChat.trim(),
          workerId: wid.trim(),
        });
        setNetworkPolicy(pol);
      } catch {
        setNetworkPolicy(null);
      }
    },
    [],
  );

  useEffect(() => {
    adminService
      .getPlaygroundConfig()
      .then(async (cfg) => {
        const workers = cfg.workers ?? [];
        const workerIds = workerOptionIds(workers);
        setWorkerOptions(workerIds);
        setChatId((prev) => prev || cfg.team_chat_id || '');
        const browserIds = new Set<string>();
        const initialPolicyChat = (cfg.team_chat_id || POLICY_CHAT_ID).trim();
        await Promise.all(
          workers.map(async (w) => {
            const wid = workerOptionId(w);
            try {
              const pol = await adminService.getSandboxChatPolicy({
                chatId: initialPolicyChat,
                workerId: wid,
              });
              if (pol.browser_sandbox) browserIds.add(wid);
            } catch {
              /* ignore per-worker policy errors */
            }
          }),
        );
        setBrowserWorkerIds(browserIds);
        setWorkerId((prev) => {
          if (prev) return prev;
          const firstBrowser = workerIds.find((wid) => browserIds.has(wid));
          return firstBrowser ?? workerIds[0] ?? '';
        });
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (workerId.trim() && policyChatId) {
      loadNetworkPolicy(workerId, policyChatId);
    }
  }, [workerId, policyChatId, loadNetworkPolicy]);

  useEffect(() => {
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [load]);

  const toggleNetwork = async () => {
    if (!workerId.trim() || !networkPolicy?.network_toggle_available) return;
    const nextOn = networkPolicy.effective_network !== 'allow';
    setNetworkToggling(true);
    setError(null);
    try {
      await adminService.setSandboxNetwork({
        chatId: policyChatId,
        enabled: nextOn,
        workerId: workerId.trim(),
      });
      await loadNetworkPolicy(workerId, policyChatId);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo cambiar la red del sandbox');
    } finally {
      setNetworkToggling(false);
    }
  };

  const prepare = async () => {
    setPreparing(true);
    setError(null);
    try {
      const r = await adminService.prepareNovncSession({
        chatId: chatId.trim() || undefined,
        workerId: workerId.trim() || undefined,
      });
      setVncUrl(r.vnc_url);
      const ttl =
        r.seconds_remaining != null ? `${Math.round(r.seconds_remaining)}s` : '—';
      setPrepareMeta(`Sesión ${r.session_id} · worker ${r.worker_id} · TTL ~${ttl}`);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo preparar noVNC');
    } finally {
      setPreparing(false);
    }
  };

  const ready = status?.ready === true;

  return (
    <PageShell>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black dark:text-dark-text flex items-center gap-2">
            <Monitor size={28} /> VNC — browser sandbox
          </h1>
          <p className="text-sm text-gov-gray-500 mt-1 max-w-2xl">
            Escritorio en vivo del contenedor Strix (Playwright / Chromium). La tabla incluye
            sandboxes compute (Python/bash) sin pantalla.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="px-3 py-2 text-sm border rounded-xl dark:border-dark-border flex items-center gap-2"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Actualizar
        </button>
      </header>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {status && !ready && (
        <div className="rounded-xl border border-amber-300/60 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-700 p-4 text-sm">
          <p className="font-bold text-amber-900 dark:text-amber-200">Requisitos no cumplidos</p>
          <ul className="mt-2 list-disc pl-5 text-amber-800 dark:text-amber-100/90 space-y-1">
            {(status.hints ?? []).map((h) => (
              <li key={h}>{h}</li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-gov-gray-500">
            Ver docs/operations/Strix-Sandbox-Security.md · STRIX_BROWSER_PUBLISH_NOVNC=1
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <section className="xl:col-span-1 space-y-4">
          <div className="rounded-2xl border dark:border-dark-border p-4 space-y-3">
            <h2 className="font-bold text-sm">Preparar sesión</h2>
            <label className="block text-xs text-gov-gray-500">
              chat_id
              <input
                value={chatId}
                onChange={(e) => setChatId(e.target.value)}
                className="mt-1 w-full px-2 py-2 text-sm font-mono border rounded-lg dark:border-dark-border dark:bg-dark-surface"
                placeholder="admin-playground"
              />
            </label>
            <label className="block text-xs text-gov-gray-500">
              Worker (browser_sandbox)
              <select
                value={workerId}
                onChange={(e) => setWorkerId(e.target.value)}
                className="mt-1 w-full px-2 py-2 text-sm border rounded-lg dark:border-dark-border dark:bg-dark-surface"
              >
                {workerOptions.map((w) => (
                  <option key={w} value={w}>
                    {w}
                    {browserWorkerIds.size > 0 && !browserWorkerIds.has(w) ? ' (sin browser)' : ''}
                  </option>
                ))}
              </select>
            </label>
            <div
              className="rounded-xl border dark:border-dark-border p-3 space-y-2"
              aria-label="Internet en sandbox"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-bold flex items-center gap-1.5">
                  <Globe size={14} /> Internet en sandbox
                </span>
                <button
                  type="button"
                  role="switch"
                  aria-checked={networkPolicy?.effective_network === 'allow'}
                  disabled={
                    networkToggling ||
                    !networkPolicy?.network_toggle_available ||
                    !workerId.trim()
                  }
                  onClick={toggleNetwork}
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
              <p className="text-[10px] text-gov-gray-500 leading-snug">
                Chat política: <code className="font-mono">{policyChatId}</code>
                {policyChatId !== POLICY_CHAT_ID && (
                  <>
                    {' '}
                    (chat flotante: <code className="font-mono">{POLICY_CHAT_ID}</code>)
                  </>
                )}
                {networkPolicy && (
                  <>
                    {' '}
                    · YAML: {networkPolicy.yaml_network_default} · efectiva:{' '}
                    {networkPolicy.effective_network}
                  </>
                )}
              </p>
              {networkPolicy && !networkPolicy.browser_sandbox && (
                <p className="text-[10px] text-amber-700 dark:text-amber-300">
                  Este worker no declara <code className="font-mono">browser_sandbox</code> en su
                  manifest; noVNC solo aplica tras <code className="font-mono">run_browser_sandbox</code>{' '}
                  en workers con navegador (p. ej. finanz, Job-Hunter, Quant-Trader).
                </p>
              )}
              {networkPolicy?.browser_sandbox && !networkPolicy.network_toggle_available && (
                <p className="text-[10px] text-amber-700 dark:text-amber-300">
                  Este worker no permite internet en sandbox (deny en YAML). Usa{' '}
                  <code className="font-mono">tavily_search</code> en el chat si aplica.
                </p>
              )}
            </div>
            <button
              type="button"
              disabled={preparing || !ready}
              onClick={prepare}
              className="w-full px-4 py-2 text-sm font-bold bg-gov-blue-700 text-white rounded-xl disabled:opacity-50"
            >
              {preparing ? 'Preparando…' : 'Preparar sesión'}
            </button>
            {prepareMeta && <p className="text-[10px] font-mono text-gov-gray-400">{prepareMeta}</p>}
            {vncUrl && (
              <a
                href={vncUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-gov-blue-700 font-semibold"
              >
                <ExternalLink size={14} /> Abrir en nueva pestaña
              </a>
            )}
          </div>

          <div className="rounded-2xl border dark:border-dark-border overflow-hidden">
            <div className="p-3 border-b dark:border-dark-border flex justify-between items-center">
              <h2 className="font-bold text-sm">Contenedores Strix</h2>
              <span className="text-xs font-mono text-gov-gray-400">{containers.length}</span>
            </div>
            <div className="max-h-[320px] overflow-auto">
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
                  {containers.map((c) => (
                    <tr key={c.session_id} className="border-t dark:border-dark-border">
                      <td className="px-2 py-2 font-mono truncate max-w-[100px]" title={c.session_id}>
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
                  {containers.length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-2 py-6 text-center text-gov-gray-400">
                        Sin contenedores activos
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <section className="xl:col-span-2">
          {vncUrl ? (
            <iframe
              title="noVNC browser sandbox"
              src={vncUrl}
              className="w-full min-h-[70vh] rounded-2xl border dark:border-dark-border bg-black"
              allow="clipboard-read; clipboard-write"
            />
          ) : (
            <div className="min-h-[70vh] rounded-2xl border border-dashed dark:border-dark-border flex items-center justify-center text-gov-gray-400 text-sm p-8 text-center">
              Pulsa «Preparar sesión» para cargar el visor noVNC. Luego ejecuta{' '}
              <code className="font-mono text-xs">run_browser_sandbox</code> desde Playground o Telegram
              con <code className="font-mono text-xs">/sandbox on</code>.
            </div>
          )}
        </section>
      </div>
    </PageShell>
  );
}
