'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { adminService } from '@/services/adminService';
import { useAuthStore } from '@/store/authStore';
import {
  Send,
  Settings2,
  Bot,
  Loader2,
  ChevronRight,
  PanelRightClose,
  PanelRightOpen,
} from 'lucide-react';

type ChatMsg = { role: 'user' | 'assistant' | 'error'; text: string; streaming?: boolean };

export default function PlaygroundPage() {
  const searchParams = useSearchParams();
  const { usuario } = useAuthStore();
  const initialWorker = searchParams.get('worker') || '';

  const [config, setConfig] = useState<Awaited<ReturnType<typeof adminService.getPlaygroundConfig>> | null>(
    null
  );
  const [workerId, setWorkerId] = useState(initialWorker);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState('');
  const [systemPreview, setSystemPreview] = useState('');
  const [loading, setLoading] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [panelOpen, setPanelOpen] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const chatId = 'admin-playground';

  const loadConfig = useCallback(() => {
    adminService
      .getPlaygroundConfig()
      .then((c) => {
        setConfig(c);
        setWorkerId((prev) => {
          if (prev) return prev;
          if (initialWorker && c.workers?.includes(initialWorker)) return initialWorker;
          if (c.workers?.includes('default')) return 'default';
          return c.workers?.[0] ?? '';
        });
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, [initialWorker]);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  useEffect(() => {
    if (!workerId) return;
    adminService
      .getTemplate(workerId)
      .then((t) => {
        const sp = t.contents['system_prompt.md'];
        setSystemPreview(typeof sp === 'string' ? sp.slice(0, 1200) : '');
      })
      .catch(() => setSystemPreview(''));
  }, [workerId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, loading, thinking]);

  const send = async () => {
    const text = input.trim();
    if (!text || loading || !workerId) return;
    setInput('');
    setLoading(true);
    setThinking(true);
    setError(null);
    setMessages((m) => [
      ...m,
      { role: 'user', text },
      { role: 'assistant', text: '', streaming: true },
    ]);

    const appendAssistant = (chunk: string) => {
      if (chunk) setThinking(false);
      setMessages((m) => {
        if (m.length === 0) return m;
        const next = [...m];
        const last = next[next.length - 1];
        if (last?.role !== 'assistant') return m;
        next[next.length - 1] = { ...last, text: last.text + chunk, streaming: true };
        return next;
      });
    };

    try {
      let assignedSuffix = '';
      await adminService.playgroundChatStream(
        {
          worker_id: workerId,
          message: text,
          chat_id: chatId,
          tenant_id: config?.effective_tenant_id ?? 'default',
        },
        {
          onToken: appendAssistant,
          onDone: (meta) => {
            if (meta.assigned_worker_id && meta.assigned_worker_id !== workerId) {
              assignedSuffix = ` (worker: ${meta.assigned_worker_id})`;
            }
          },
        }
      );
      setMessages((m) => {
        if (m.length === 0) return m;
        const next = [...m];
        const last = next[next.length - 1];
        if (last?.role === 'assistant') {
          const base = last.text || '(sin respuesta)';
          next[next.length - 1] = {
            role: 'assistant',
            text: base + assignedSuffix,
            streaming: false,
          };
        }
        return next;
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Error';
      setMessages((m) => {
        const trimmed =
          m.length > 0 && m[m.length - 1]?.role === 'assistant' && m[m.length - 1]?.streaming
            ? m.slice(0, -1)
            : m;
        return [...trimmed, { role: 'error', text: msg }];
      });
      setError(msg);
    } finally {
      setLoading(false);
      setThinking(false);
    }
  };

  const activeCatalog = config?.catalog?.find((c) => c.active);

  return (
    <div className="flex flex-col lg:flex-row gap-4 min-h-[calc(100vh-8rem)] relative">
      <section className="flex-1 flex flex-col min-w-0 bg-white dark:bg-dark-surface rounded-3xl border dark:border-dark-border shadow-sm overflow-hidden">
        <header className="flex flex-wrap items-center justify-between gap-3 p-4 border-b dark:border-dark-border">
          <div>
            <h1 className="text-xl font-black dark:text-dark-text flex items-center gap-2">
              <Bot size={22} /> Playground
            </h1>
            <p className="text-xs text-gov-gray-500 mt-0.5">
              Respuestas en vivo (SSE) — el modelo lo define el gateway (.env)
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap justify-end">
            <button
              type="button"
              onClick={() => setPanelOpen((o) => !o)}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-xl border dark:border-dark-border text-gov-gray-600 dark:text-dark-muted hover:bg-gov-gray-50 dark:hover:bg-dark-bg transition-colors"
              title={panelOpen ? 'Ocultar panel lateral' : 'Mostrar panel lateral'}
            >
              {panelOpen ? <PanelRightClose size={16} /> : <PanelRightOpen size={16} />}
              {panelOpen ? 'Ocultar panel' : 'Panel'}
            </button>
            <label className="text-xs font-bold text-gov-gray-500">Agente</label>
            <select
              value={workerId}
              onChange={(e) => {
                setWorkerId(e.target.value);
                setMessages([]);
              }}
              className="text-sm px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-bg max-w-[200px]"
            >
              {(config?.workers ?? []).map((w) => (
                <option key={w} value={w}>
                  {w}
                </option>
              ))}
            </select>
            <Link
              href={`/templates/${workerId}`}
              className="text-xs text-gov-blue-700 font-semibold flex items-center gap-1"
            >
              Editar <ChevronRight size={12} />
            </Link>
          </div>
        </header>

        <div
          ref={scrollRef}
          className={`flex-1 overflow-y-auto p-4 space-y-4 min-h-[320px] ${
            panelOpen ? 'max-h-[55vh] lg:max-h-[58vh]' : 'max-h-[calc(100vh-14rem)] lg:max-h-[72vh]'
          }`}
        >
          {messages.length === 0 && (
            <p className="text-sm text-gov-gray-400 text-center py-16">
              Escribe un mensaje abajo para probar <strong>{workerId || '…'}</strong>
            </p>
          )}
          {messages.map((m, i) => {
            const isEmptyStreaming =
              m.role === 'assistant' && m.streaming && !m.text && thinking && i === messages.length - 1;
            if (isEmptyStreaming) {
              return <ThinkingBubble key={`${i}-thinking`} />;
            }
            return (
              <div
                key={`${i}-${m.role}`}
                className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm whitespace-pre-wrap ${
                  m.role === 'user'
                    ? 'ml-auto bg-gov-blue-700 text-white'
                    : m.role === 'error'
                      ? 'bg-red-50 text-red-800 border border-red-200'
                      : 'bg-gov-gray-50 dark:bg-dark-bg border dark:border-dark-border'
                }`}
              >
                {m.text}
                {m.streaming && m.text && (
                  <span className="inline-block w-2 h-4 ml-0.5 bg-gov-blue-600 animate-pulse align-middle" />
                )}
              </div>
            );
          })}
        </div>

        <footer className="p-4 border-t dark:border-dark-border bg-gov-gray-50/50 dark:bg-dark-bg/50">
          <div className="flex gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              rows={2}
              placeholder="Escribe tu mensaje… (Enter envía, Shift+Enter nueva línea)"
              className="flex-1 px-3 py-2 text-sm border rounded-xl dark:border-dark-border dark:bg-dark-surface resize-none"
              disabled={loading || usuario?.rol !== 'admin'}
            />
            <button
              type="button"
              onClick={send}
              disabled={loading || !input.trim() || usuario?.rol !== 'admin'}
              className="px-4 py-2 bg-gov-blue-700 text-white rounded-xl font-bold text-sm flex items-center gap-2 disabled:opacity-50 shrink-0"
            >
              <Send size={18} /> Run
            </button>
          </div>
          {error && <p className="text-xs text-red-600 mt-2">{error}</p>}
        </footer>
      </section>

      {!panelOpen && (
        <button
          type="button"
          onClick={() => setPanelOpen(true)}
          className="hidden lg:flex fixed right-6 top-1/2 -translate-y-1/2 z-20 items-center gap-1 px-2 py-3 rounded-l-2xl bg-white dark:bg-dark-surface border border-r-0 dark:border-dark-border shadow-md text-xs font-bold text-gov-blue-700 hover:bg-gov-gray-50 dark:hover:bg-dark-bg"
          title="Mostrar panel lateral"
        >
          <PanelRightOpen size={18} />
        </button>
      )}

      <aside
        className={`shrink-0 overflow-hidden transition-[width,opacity] duration-300 ease-out ${
          panelOpen
            ? 'w-full lg:w-80 opacity-100'
            : 'w-0 max-w-0 opacity-0 pointer-events-none lg:hidden'
        }`}
        aria-hidden={!panelOpen}
      >
        <div className="w-full lg:w-80 space-y-4">
        <div className="flex items-center justify-between lg:hidden">
          <span className="text-xs font-bold uppercase text-gov-gray-500">Configuración</span>
          <button
            type="button"
            onClick={() => setPanelOpen(false)}
            className="p-2 rounded-lg hover:bg-gov-gray-100 dark:hover:bg-dark-bg"
            aria-label="Cerrar panel"
          >
            <PanelRightClose size={18} />
          </button>
        </div>
        <section className="bg-white dark:bg-dark-surface rounded-3xl border dark:border-dark-border p-4 space-y-3">
          <h2 className="font-bold text-sm flex items-center gap-2">
            <Settings2 size={18} /> Run settings
          </h2>
          <p className="text-[10px] text-gov-gray-500">{config?.note}</p>

          <div className="rounded-xl bg-gov-gray-50 dark:bg-dark-bg p-3 text-xs space-y-2">
            <Row label="Proveedor activo" value={config?.llm?.provider || '—'} highlight />
            <Row label="Modelo" value={config?.llm?.model || '—'} />
            <Row label="Base URL" value={config?.llm?.base_url || '—'} mono />
            {activeCatalog && (
              <p className="text-[10px] text-gov-gray-500 pt-1">{activeCatalog.hint}</p>
            )}
          </div>

          <Link href="/settings" className="text-xs text-gov-blue-700 font-semibold block">
            Cambiar en Ajustes (.env) →
          </Link>
        </section>

        <section className="bg-white dark:bg-dark-surface rounded-3xl border dark:border-dark-border p-4">
          <h3 className="font-bold text-xs uppercase text-gov-gray-500 mb-2">
            Proveedores disponibles
          </h3>
          <ul className="space-y-2 max-h-48 overflow-y-auto text-xs">
            {(config?.catalog ?? []).map((p) => (
              <li
                key={p.id}
                className={`p-2 rounded-lg border ${
                  p.active
                    ? 'border-gov-blue-500 bg-gov-blue-50 dark:bg-dark-bg'
                    : 'border-transparent bg-gov-gray-50 dark:bg-dark-bg'
                }`}
              >
                <p className="font-bold">{p.label}</p>
                <p className="text-gov-gray-500">{p.kind === 'local' ? 'Local' : 'API'}</p>
                {p.env_keys?.length > 0 && (
                  <p className="font-mono text-[10px] mt-1">{p.env_keys.join(', ')}</p>
                )}
              </li>
            ))}
          </ul>
        </section>

        <section className="bg-white dark:bg-dark-surface rounded-3xl border dark:border-dark-border p-4">
          <h3 className="font-bold text-xs uppercase text-gov-gray-500 mb-2">
            Instrucciones del agente
          </h3>
          <pre className="text-[10px] font-mono whitespace-pre-wrap max-h-40 overflow-y-auto text-gov-gray-600 dark:text-dark-muted">
            {systemPreview || 'Sin system_prompt.md'}
          </pre>
          <Link
            href={`/templates/${workerId}?focus=system_prompt.md`}
            className="text-xs text-gov-blue-700 font-semibold mt-2 inline-block"
          >
            Editar comportamiento →
          </Link>
        </section>

        <ProviderGuide />
        </div>
      </aside>
    </div>
  );
}

function ThinkingBubble() {
  return (
    <div
      className="max-w-[85%] flex items-center gap-3 rounded-2xl px-4 py-3 bg-gov-gray-50 dark:bg-dark-bg border dark:border-dark-border"
      role="status"
      aria-live="polite"
      aria-label="Pensando"
    >
      <div className="relative flex h-9 w-9 shrink-0 items-center justify-center">
        <span className="absolute inset-0 rounded-full border-2 border-gov-blue-200 dark:border-gov-blue-900" />
        <Loader2 className="h-6 w-6 animate-spin text-gov-blue-700 dark:text-dark-cyan" aria-hidden />
      </div>
      <div>
        <p className="text-sm font-semibold text-gov-gray-700 dark:text-dark-text">Pensando…</p>
        <p className="text-xs text-gov-gray-500 dark:text-dark-muted">Generando respuesta</p>
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  mono,
  highlight,
}: {
  label: string;
  value: string;
  mono?: boolean;
  highlight?: boolean;
}) {
  return (
    <div>
      <p className="text-gov-gray-500">{label}</p>
      <p
        className={`${mono ? 'font-mono break-all' : ''} ${highlight ? 'font-bold text-gov-blue-800 dark:text-dark-cyan' : ''}`}
      >
        {value}
      </p>
    </div>
  );
}

function ProviderGuide() {
  return (
    <details className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 rounded-2xl p-3 text-xs">
      <summary className="font-bold cursor-pointer">¿API o Ollama local?</summary>
      <div className="mt-2 space-y-2 text-gov-gray-700 dark:text-dark-muted">
        <p>
          <strong>API (nube):</strong> DeepSeek, OpenAI, Groq, Gemini… Pon la API key en{' '}
          <code>.env</code> y define <code>DUCKCLAW_LLM_PROVIDER</code>,{' '}
          <code>DUCKCLAW_LLM_MODEL</code>, <code>DUCKCLAW_LLM_BASE_URL</code>.
        </p>
        <p>
          <strong>Ollama (local):</strong> Instala Ollama, ejecuta{' '}
          <code>ollama pull llama3.2</code>, luego en .env:{' '}
          <code>DUCKCLAW_LLM_PROVIDER=ollama</code>,{' '}
          <code>DUCKCLAW_LLM_BASE_URL=http://localhost:11434</code>,{' '}
          <code>DUCKCLAW_LLM_MODEL=llama3.2</code>.
        </p>
        <p>
          <strong>MLX (Mac):</strong> Servidor local en puerto 8080 —{' '}
          <code>DUCKCLAW_LLM_PROVIDER=mlx</code> y arranca MLX con PM2 antes del gateway.
        </p>
        <p className="text-[10px]">Tras cambiar .env: reinicia DuckClaw-Gateway (Overview → Operaciones).</p>
      </div>
    </details>
  );
}
