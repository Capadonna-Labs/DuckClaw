'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Bot, Copy, MessageCircle, Trash2, UserPlus } from 'lucide-react';

import { contactsApi, type Contact } from '@/services/admin/contactsApi';
import { messagesApi } from '@/services/admin/messagesApi';

/** People of other DuckClaw instances, added by invitation code, with the agents that write for them. */
export default function ContactsPage() {
  const router = useRouter();
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [canInvite, setCanInvite] = useState(false);
  const [code, setCode] = useState('');
  const [expires, setExpires] = useState('');
  const [paste, setPaste] = useState('');
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    contactsApi
      .listContacts()
      .then((r) => { setContacts(r.contacts); setCanInvite(r.can_invite); })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);
  useEffect(load, [load]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const invite = () => run(async () => {
    const r = await contactsApi.inviteContact();
    setCode(r.code);
    setExpires(r.expires_at);
  });
  const accept = () => run(async () => {
    const r = await contactsApi.acceptContact(paste.trim());
    setPaste('');
    setNote(`Agregado: ${r.name}`);
    window.setTimeout(load, 1500); // the DB-Writer stores it in a moment
  });
  const remove = (c: Contact) => {
    if (!window.confirm(`¿Quitar a ${c.name}? Ya no podrán escribirse hasta que vuelvan a invitarse.`)) return;
    void run(async () => {
      await contactsApi.removeContact(c.id);
      window.setTimeout(load, 1500);
    });
  };
  const message = (c: Contact) => run(async () => {
    const r = await messagesApi.createMessageChannel({ kind: 'dm', members: [c.email] });
    router.push(`/playground?channel=${encodeURIComponent(r.channel_id)}`);
  });

  return (
    <section className="max-w-3xl mx-auto grid gap-4 p-4">
      <header>
        <h1 className="text-xl font-black dark:text-dark-text">Contactos</h1>
        <p className="text-xs text-gov-gray-500 mt-0.5">Personas de otras instancias de DuckClaw. Se agregan con un código de invitación.</p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-2xl border dark:border-dark-border p-4 grid gap-2 content-start">
          <p className="font-bold text-sm dark:text-dark-text flex items-center gap-1.5"><UserPlus size={15} /> Invitar</p>
          <p className="text-xs text-gov-gray-500">Genera un código y pásaselo a la persona; lo pega en Contactos de su DuckClaw. Sirve una vez y vence en 7 días.</p>
          {canInvite ? (
            <button type="button" disabled={busy} onClick={() => void invite()} className="justify-self-start rounded-xl bg-gov-blue-700 px-3 py-2 text-xs font-bold text-white disabled:opacity-50">
              Generar código
            </button>
          ) : (
            <p className="text-xs text-amber-700 dark:text-amber-300">Esta instancia no tiene DUCKCLAW_FEDERATION_URL: puede aceptar invitaciones, no enviarlas.</p>
          )}
          {code ? (
            <div className="grid gap-1">
              <textarea readOnly value={code} rows={3} className="rounded-xl border dark:border-dark-border bg-transparent p-2 text-[11px] font-mono dark:text-dark-text break-all" />
              <button type="button" onClick={() => void navigator.clipboard.writeText(code)} className="justify-self-start flex items-center gap-1 text-xs font-bold text-gov-blue-700 dark:text-dark-cyan">
                <Copy size={13} /> Copiar · vence {expires.slice(0, 10)}
              </button>
            </div>
          ) : null}
        </div>
        <div className="rounded-2xl border dark:border-dark-border p-4 grid gap-2 content-start">
          <p className="font-bold text-sm dark:text-dark-text">Tengo un código</p>
          <textarea
            value={paste}
            onChange={(e) => setPaste(e.target.value)}
            rows={3}
            placeholder="Pega aquí el código que te enviaron"
            className="rounded-xl border dark:border-dark-border bg-transparent p-2 text-[11px] font-mono dark:text-dark-text"
          />
          <button type="button" disabled={busy || paste.trim().length < 20} onClick={() => void accept()} className="justify-self-start rounded-xl bg-gov-blue-700 px-3 py-2 text-xs font-bold text-white disabled:opacity-50">
            Agregar contacto
          </button>
        </div>
      </div>

      {note ? <p className="text-sm text-emerald-700 dark:text-emerald-300">{note}</p> : null}
      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      <ul className="grid gap-2">
        {contacts.length === 0 ? <li className="text-sm text-gov-gray-400 text-center py-8">Sin contactos todavía</li> : null}
        {contacts.map((c) => (
          <li key={c.id} className="flex items-center gap-3 rounded-2xl border dark:border-dark-border p-3">
            <div className="min-w-0 flex-1">
              <p className="font-bold text-sm dark:text-dark-text truncate">{c.name}</p>
              <p className="text-xs text-gov-gray-500 truncate">{c.email} · {c.instance}</p>
              {c.agents.length ? (
                <p className="mt-1 flex flex-wrap gap-1">
                  {c.agents.map((a) => (
                    <span key={a} className="inline-flex items-center gap-1 rounded-full bg-gov-gray-100 dark:bg-dark-bg px-2 py-0.5 text-[11px] dark:text-dark-text">
                      <Bot size={11} /> {a}
                    </span>
                  ))}
                </p>
              ) : null}
            </div>
            <button type="button" disabled={busy} onClick={() => void message(c)} className="rounded-xl border dark:border-dark-border p-2" aria-label={`Mensaje a ${c.name}`} title="Mensaje">
              <MessageCircle size={15} />
            </button>
            <button type="button" disabled={busy} onClick={() => remove(c)} className="rounded-xl border border-red-200 bg-red-50 p-2 text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300" aria-label={`Quitar a ${c.name}`} title="Quitar">
              <Trash2 size={15} />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
