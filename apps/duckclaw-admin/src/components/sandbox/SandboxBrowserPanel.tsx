'use client';

import { useCallback, useEffect, useState } from 'react';
import { ExternalLink } from 'lucide-react';
import { adminService } from '@/services/adminService';
import { workerOptionId, workerOptionIds } from '@/lib/workerOptions';

type SandboxStatus = Awaited<ReturnType<typeof adminService.getSandboxStatus>> | null;

type SandboxBrowserPanelProps = {
  defaultChatId: string;
  status: SandboxStatus;
};

export function SandboxBrowserPanel({ defaultChatId, status }: SandboxBrowserPanelProps) {
  const [chatId, setChatId] = useState(defaultChatId);
  const [workerId, setWorkerId] = useState('');
  const [workerOptions, setWorkerOptions] = useState<string[]>([]);
  const [browserWorkerIds, setBrowserWorkerIds] = useState<Set<string>>(new Set());
  const [vncUrl, setVncUrl] = useState<string | null>(null);
  const [prepareMeta, setPrepareMeta] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [preparing, setPreparing] = useState(false);

  const ready = status?.ready === true;

  useEffect(() => {
    setChatId((prev) => prev || defaultChatId);
  }, [defaultChatId]);

  useEffect(() => {
    adminService
      .getPlaygroundConfig()
      .then(async (cfg) => {
        const workers = cfg.workers ?? [];
        const workerIds = workerOptionIds(workers);
        setWorkerOptions(workerIds);
        const policyChat = (defaultChatId || cfg.team_chat_id || '').trim();
        const browserIds = new Set<string>();
        await Promise.all(
          workers.map(async (w) => {
            const wid = workerOptionId(w);
            try {
              const pol = await adminService.getSandboxChatPolicy({
                chatId: policyChat,
                workerId: wid,
              });
              if (pol.browser_sandbox) browserIds.add(wid);
            } catch {
              /* ignore */
            }
          })
        );
        setBrowserWorkerIds(browserIds);
        setWorkerId((prev) => {
          if (prev) return prev;
          const firstBrowser = workerIds.find((wid) => browserIds.has(wid));
          return firstBrowser ?? workerIds[0] ?? '';
        });
      })
      .catch(() => undefined);
  }, [defaultChatId]);

  const prepare = useCallback(async () => {
    setPreparing(true);
    setError(null);
    try {
      const r = await adminService.prepareNovncSession({
        chatId: chatId.trim() || undefined,
        workerId: workerId.trim() || undefined,
      });
      setVncUrl(r.vnc_url);
      const ttl = r.seconds_remaining != null ? `${Math.round(r.seconds_remaining)}s` : '—';
      setPrepareMeta(`Sesión ${r.session_id} · worker ${r.worker_id} · TTL ~${ttl}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo preparar noVNC');
    } finally {
      setPreparing(false);
    }
  }, [chatId, workerId]);

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
      <section className="xl:col-span-1 space-y-3 rounded-2xl border dark:border-dark-border p-4">
        <h2 className="font-bold text-sm">noVNC — browser sandbox</h2>
        <label className="block text-xs text-gov-gray-500">
          chat_id
          <input
            value={chatId}
            onChange={(e) => setChatId(e.target.value)}
            className="mt-1 w-full px-2 py-2 text-sm font-mono border rounded-lg dark:border-dark-border dark:bg-dark-surface"
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
        <button
          type="button"
          disabled={preparing || !ready}
          onClick={() => void prepare()}
          className="w-full px-4 py-2 text-sm font-bold bg-gov-blue-700 text-white rounded-xl disabled:opacity-50"
        >
          {preparing ? 'Preparando…' : 'Preparar sesión'}
        </button>
        {prepareMeta ? <p className="text-[10px] font-mono text-gov-gray-400">{prepareMeta}</p> : null}
        {vncUrl ? (
          <a
            href={vncUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-gov-blue-700 font-semibold"
          >
            <ExternalLink size={14} /> Abrir en nueva pestaña
          </a>
        ) : null}
        {error ? <p className="text-xs text-red-600">{error}</p> : null}
      </section>

      <section className="xl:col-span-2">
        {vncUrl ? (
          <iframe
            title="noVNC browser sandbox"
            src={vncUrl}
            className="w-full min-h-[65vh] rounded-2xl border dark:border-dark-border bg-black"
            allow="clipboard-read; clipboard-write"
          />
        ) : (
          <div className="min-h-[65vh] rounded-2xl border border-dashed dark:border-dark-border flex items-center justify-center text-gov-gray-400 text-sm p-8 text-center">
            Prepara la sesión y ejecuta <code className="font-mono text-xs">run_browser_sandbox</code>{' '}
            desde Chat con <code className="font-mono text-xs">/sandbox on</code>.
          </div>
        )}
      </section>
    </div>
  );
}
