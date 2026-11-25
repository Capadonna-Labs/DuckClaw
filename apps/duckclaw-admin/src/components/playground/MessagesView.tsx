'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeft, Bot, Plus, Send, Users, User } from 'lucide-react';

import { messagesApi, type ChannelMessage, type MessageChannel } from '@/services/admin/messagesApi';
import { formatConversationTime } from './playgroundHistoryHelpers';

// ponytail: polling (4 s open channel, 15 s list); SSE if it ever needs to be instant.
const OPEN_MS = 4_000;
const LIST_MS = 15_000;

/** Direct messages and groups between console users (and the coding agents that write for them). */
export function MessagesView({ initialChannel = '' }: { initialChannel?: string }) {
  const [channels, setChannels] = useState<MessageChannel[]>([]);
  const [openId, setOpenId] = useState(initialChannel);
  const [open, setOpen] = useState<(MessageChannel & { messages: ChannelMessage[] }) | null>(null);
  const [pending, setPending] = useState<ChannelMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  const loadList = useCallback(() => {
    messagesApi.channels().then((r) => setChannels(r.channels)).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(() => {
    loadList();
    const t = window.setInterval(loadList, LIST_MS);
    return () => window.clearInterval(t);
  }, [loadList]);

  useEffect(() => {
    if (!openId) return;
    let cancelled = false;
    const load = () =>
      messagesApi
        .read(openId)
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
  }, [openId]);

  const shown = [...(open?.id === openId ? open.messages : []), ...pending];
  useEffect(() => bottom.current?.scrollIntoView({ block: 'end' }), [shown.length]);

  const send = async () => {
    const body = draft.trim();
    if (!body || !openId) return;
    setDraft('');
    setPending((p) => [...p, { id: `p${Date.now()}`, author_email: '', author: 'Tú', agent: false, body, created_at: '', mine: true }]);
    try {
      await messagesApi.post(openId, body);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  if (creating) {
    return <NewChannel onCancel={() => setCreating(false)} onCreated={(id) => { setCreating(false); setOpenId(id); setOpen(null); loadList(); }} />;
  }

  return (
    <div className="flex h-full min-h-0 gap-3">
      <aside className={`${openId ? 'hidden lg:flex' : 'flex'} w-full lg:w-72 shrink-0 flex-col gap-2 min-h-0`}>
        <button
          type="button"
          onClick={() => setCreating(true)}
          className="flex items-center justify-center gap-1.5 rounded-xl bg-gov-blue-700 px-3 py-2 text-xs font-bold text-white hover:bg-gov-blue-800"
        >
          <Plus size={14} /> Nuevo mensaje o grupo
        </button>
        {error ? <p className="text-xs text-red-600">{error}</p> : null}
        <ul className="grid gap-2 overflow-y-auto scrollbar-thin">
          {channels.length === 0 ? <li className="text-sm text-gov-gray-400 text-center py-8">Sin mensajes todavía</li> : null}
          {channels.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => { setOpenId(c.id); setOpen(null); setPending([]); }}
                className={`w-full text-left rounded-2xl border dark:border-dark-border p-3 hover:border-gov-blue-300 ${c.id === openId ? 'border-gov-blue-400 bg-gov-blue-50/60 dark:bg-dark-bg' : ''}`}
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-1.5 font-bold text-sm dark:text-dark-text truncate">
                    {c.kind === 'group' ? <Users size={14} /> : <User size={14} />} {c.name}
                  </span>
                  <span className="text-[10px] font-bold uppercase text-gov-gray-400 whitespace-nowrap">{formatConversationTime(c.updated_at ?? '')}</span>
                </span>
                <span className="block text-xs text-gov-gray-500 mt-1 line-clamp-2">{c.last_message_preview || 'Sin mensajes todavía'}</span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      {openId ? (
        <section className="flex flex-1 min-w-0 min-h-0 flex-col rounded-2xl border dark:border-dark-border">
          <header className="flex items-center gap-2 border-b dark:border-dark-border p-3">
            <button type="button" className="lg:hidden" onClick={() => setOpenId('')} aria-label="Volver a la lista">
              <ArrowLeft size={18} />
            </button>
            <div className="min-w-0">
              <p className="font-bold text-sm dark:text-dark-text truncate">{open?.name || channels.find((c) => c.id === openId)?.name || 'Creando…'}</p>
              <p className="text-[11px] text-gov-gray-500 truncate">{open?.members.join(', ')}</p>
            </div>
          </header>
          <div className="flex-1 min-h-0 overflow-y-auto scrollbar-thin p-3 grid content-start gap-2">
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
          <form
            className="flex gap-2 border-t dark:border-dark-border p-2"
            onSubmit={(e) => { e.preventDefault(); void send(); }}
          >
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
      ) : (
        <p className="hidden lg:flex flex-1 items-center justify-center text-sm text-gov-gray-400">Elige una conversación</p>
      )}
    </div>
  );
}

function NewChannel({ onCancel, onCreated }: { onCancel: () => void; onCreated: (id: string) => void }) {
  const [people, setPeople] = useState<{ email: string; name: string }[]>([]);
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
    <div className="grid gap-3 max-w-md">
      <p className="font-bold dark:text-dark-text">Nuevo mensaje</p>
      <p className="text-xs text-gov-gray-500">Una persona = mensaje directo. Varias = grupo (ponle nombre).</p>
      <ul className="grid gap-1 max-h-64 overflow-y-auto scrollbar-thin">
        {people.map((p) => (
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
