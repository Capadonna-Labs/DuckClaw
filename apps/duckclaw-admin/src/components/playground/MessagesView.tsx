'use client';

import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, Bot, Send } from 'lucide-react';

import { messagesApi, type ChannelMessage, type MessageChannel } from '@/services/admin/messagesApi';
import { formatConversationTime } from './playgroundHistoryHelpers';

// ponytail: 4 s polling of the open channel; SSE if it ever needs to be instant.
const OPEN_MS = 4_000;

/** One direct message or group, opened from the Historial list (people and the coding agents that write for them). */
export function ChannelChat({ channelId, fallbackName = '', onBack }: { channelId: string; fallbackName?: string; onBack: () => void }) {
  const [open, setOpen] = useState<(MessageChannel & { messages: ChannelMessage[] }) | null>(null);
  const [pending, setPending] = useState<ChannelMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      messagesApi
        .read(channelId)
        .then((c) => {
          if (cancelled) return;
          setOpen(c);
          setPending((p) => p.filter((m) => !c.messages.some((x) => x.mine && x.body === m.body)));
        })
        .catch(() => undefined); // a channel just created is not readable until the DB-Writer commits it
    void load();
    const t = window.setInterval(load, OPEN_MS);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [channelId]);

  const shown = [...(open?.messages ?? []), ...pending];
  useEffect(() => bottom.current?.scrollIntoView({ block: 'end' }), [shown.length]);

  const send = async () => {
    const body = draft.trim();
    if (!body) return;
    setDraft('');
    setPending((p) => [...p, { id: `p${Date.now()}`, author_email: '', author: 'Tú', agent: false, body, created_at: '', mine: true }]);
    try {
      await messagesApi.post(channelId, body);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <section className="flex h-full min-h-0 flex-col">
      <header className="flex items-center gap-2 border-b dark:border-dark-border p-3">
        <button type="button" onClick={onBack} aria-label="Volver al historial">
          <ArrowLeft size={18} />
        </button>
        <div className="min-w-0">
          <p className="font-bold text-sm dark:text-dark-text truncate">{open?.name || fallbackName || 'Creando…'}</p>
          <p className="text-[11px] text-gov-gray-500 truncate">{open?.members.join(', ')}</p>
        </div>
      </header>
      <div className="flex-1 min-h-0 overflow-y-auto scrollbar-thin p-3 grid content-start gap-2">
        {shown.length === 0 ? <p className="text-sm text-gov-gray-400 text-center py-8">Sin mensajes todavía</p> : null}
        {shown.map((m) => (
          <div key={m.id} className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${m.mine ? 'justify-self-end bg-gov-blue-700 text-white' : 'justify-self-start bg-gov-gray-100 dark:bg-dark-bg dark:text-dark-text'}`}>
            <p className={`flex items-center gap-1 text-[10px] font-bold ${m.mine ? 'text-blue-100' : 'text-gov-gray-500'}`}>
              {m.agent ? <Bot size={11} aria-label="agente" /> : null}
              {m.mine && !m.agent ? 'Tú' : m.author}
              {m.created_at ? ` · ${formatConversationTime(m.created_at)}` : ' · enviando…'}
            </p>
            <p className="whitespace-pre-wrap break-words">{m.body}</p>
          </div>
        ))}
        <div ref={bottom} />
      </div>
      {error ? <p className="px-3 text-xs text-red-600">{error}</p> : null}
      <form className="flex gap-2 border-t dark:border-dark-border p-2" onSubmit={(e) => { e.preventDefault(); void send(); }}>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send(); } }}
          rows={1}
          maxLength={8000}
          placeholder="Escribe un mensaje"
          className="flex-1 resize-none rounded-xl border dark:border-dark-border bg-transparent px-3 py-2 text-sm dark:text-dark-text"
        />
        <button type="submit" disabled={!draft.trim()} className="rounded-xl bg-gov-blue-700 px-3 text-white disabled:opacity-50" aria-label="Enviar">
          <Send size={16} />
        </button>
      </form>
    </section>
  );
}

export function NewChannel({ onCancel, onCreated }: { onCancel: () => void; onCreated: (id: string) => void }) {
  const [people, setPeople] = useState<{ email: string; name: string }[] | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    messagesApi.people().then(setPeople).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const isGroup = picked.length > 1;
  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await messagesApi.createChannel({ kind: isGroup ? 'group' : 'dm', name: isGroup ? name.trim() : '', members: picked });
      onCreated(r.channel_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-3 max-w-md p-4">
      <p className="font-bold dark:text-dark-text">Nuevo mensaje o grupo</p>
      <p className="text-xs text-gov-gray-500">Una persona = mensaje directo. Varias = grupo (ponle nombre).</p>
      {people && people.length === 0 ? (
        <p className="text-sm text-gov-gray-500">No hay más usuarios en la consola. Créalos en Administración › Acceso.</p>
      ) : null}
      <ul className="grid gap-1 max-h-64 overflow-y-auto scrollbar-thin">
        {(people ?? []).map((p) => (
          <li key={p.email}>
            <label className="flex items-center gap-2 text-sm dark:text-dark-text">
              <input
                type="checkbox"
                checked={picked.includes(p.email)}
                onChange={(e) => setPicked((s) => (e.target.checked ? [...s, p.email] : s.filter((x) => x !== p.email)))}
              />
              {p.name} <span className="text-xs text-gov-gray-400">{p.email}</span>
            </label>
          </li>
        ))}
      </ul>
      {isGroup ? (
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={80}
          placeholder="Nombre del grupo"
          className="rounded-xl border dark:border-dark-border bg-transparent px-3 py-2 text-sm dark:text-dark-text"
        />
      ) : null}
      {error ? <p className="text-xs text-red-600">{error}</p> : null}
      <div className="flex gap-2">
        <button type="button" onClick={onCancel} className="rounded-xl border dark:border-dark-border px-3 py-2 text-xs font-bold">Cancelar</button>
        <button
          type="button"
          disabled={busy || picked.length === 0 || (isGroup && !name.trim())}
          onClick={() => void create()}
          className="rounded-xl bg-gov-blue-700 px-3 py-2 text-xs font-bold text-white disabled:opacity-50"
        >
          {isGroup ? 'Crear grupo' : 'Abrir mensaje directo'}
        </button>
      </div>
    </div>
  );
}
