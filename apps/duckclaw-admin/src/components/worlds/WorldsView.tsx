'use client';

import { useCallback, useEffect, useState } from 'react';
import { Bot, Globe, Loader2, Pencil, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { worldsApi } from '@/services/admin/worldsApi';
import {
  ageLabel,
  botDraftOf,
  parseJsonObject,
  worldDraftOf,
  type BotDraft,
  type BotStatus,
  type World,
  type WorldBot,
  type WorldDraft,
} from '@/lib/worldsTypes';

const REFRESH_MS = 15_000;
const INPUT = 'px-2 py-2 text-sm border rounded-xl dark:border-dark-border bg-white dark:bg-dark-surface w-full';
const BTN = 'px-3 py-2 text-sm border rounded-xl dark:border-dark-border inline-flex items-center gap-2 disabled:opacity-50';

const STATUS_STYLE: Record<BotStatus, string> = {
  online: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
  starting: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  error: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
  offline: 'bg-gov-gray-100 text-gov-gray-600 dark:bg-dark-surface dark:text-gov-gray-400',
  unknown: 'bg-gov-gray-100 text-gov-gray-600 dark:bg-dark-surface dark:text-gov-gray-400',
};

function StatusBadge({ bot }: { bot: WorldBot }) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_STYLE[bot.status] ?? STATUS_STYLE.unknown}`} title={bot.status_detail || undefined}>
      {bot.status} · {ageLabel(bot.seconds_since_report)}
    </span>
  );
}

function JsonField({ label, hint, value, onChange }: { label: string; hint: string; value: string; onChange: (v: string) => void }) {
  const check = parseJsonObject(value);
  return (
    <label className="block text-sm space-y-1">
      <span className="text-gov-gray-500">{label}</span>
      <textarea className={`${INPUT} font-mono min-h-[7rem]`} value={value} onChange={(e) => onChange(e.target.value)} spellCheck={false} />
      <span className={`text-xs ${'error' in check ? 'text-red-600' : 'text-gov-gray-500'}`}>{'error' in check ? check.error : hint}</span>
    </label>
  );
}

function WorldForm({ initial, onSave, onCancel }: { initial: WorldDraft; onSave: (d: WorldDraft) => Promise<void>; onCancel: () => void }) {
  const [d, setD] = useState(initial);
  const [saving, setSaving] = useState(false);
  const bad = 'error' in parseJsonObject(d.config) || !d.name.trim();
  const set = <K extends keyof WorldDraft>(k: K, v: WorldDraft[K]) => setD((p) => ({ ...p, [k]: v }));
  return (
    <div className="border rounded-2xl p-4 space-y-3 dark:border-dark-border">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm space-y-1 block"><span className="text-gov-gray-500">Nombre</span>
          <input className={INPUT} value={d.name} onChange={(e) => set('name', e.target.value)} maxLength={80} /></label>
        <label className="text-sm space-y-1 block"><span className="text-gov-gray-500">Tipo (lo define tu extensión, p. ej. minecraft)</span>
          <input className={INPUT} value={d.kind} onChange={(e) => set('kind', e.target.value.toLowerCase())} placeholder="generic" /></label>
        <label className="text-sm space-y-1 block"><span className="text-gov-gray-500">Host o IP</span>
          <input className={INPUT} value={d.host} onChange={(e) => set('host', e.target.value)} placeholder="100.99.72.63" /></label>
        <label className="text-sm space-y-1 block"><span className="text-gov-gray-500">Puerto</span>
          <input className={INPUT} value={d.port} onChange={(e) => set('port', e.target.value.replace(/\D/g, ''))} inputMode="numeric" placeholder="25565" /></label>
      </div>
      <JsonField label="Configuración (JSON libre)" hint="Lo que lea tu runner: edición, versión, plugins, lista blanca… Sin claves ni tokens: van en el entorno del runner."
        value={d.config} onChange={(v) => set('config', v)} />
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={d.enabled} onChange={(e) => set('enabled', e.target.checked)} /> Habilitado</label>
      <div className="flex gap-2">
        <button className={BTN} disabled={bad || saving} onClick={async () => { setSaving(true); try { await onSave(d); } finally { setSaving(false); } }}>
          {saving ? <Loader2 size={16} className="animate-spin" /> : null} Guardar
        </button>
        <button className={BTN} onClick={onCancel}>Cancelar</button>
      </div>
    </div>
  );
}

function BotForm({ initial, onSave, onCancel }: { initial: BotDraft; onSave: (d: BotDraft) => Promise<void>; onCancel: () => void }) {
  const [d, setD] = useState(initial);
  const [saving, setSaving] = useState(false);
  const bad = 'error' in parseJsonObject(d.settings) || !d.name.trim();
  const set = <K extends keyof BotDraft>(k: K, v: BotDraft[K]) => setD((p) => ({ ...p, [k]: v }));
  return (
    <div className="border rounded-xl p-3 space-y-3 dark:border-dark-border">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm space-y-1 block"><span className="text-gov-gray-500">Nombre del bot</span>
          <input className={INPUT} value={d.name} onChange={(e) => set('name', e.target.value)} maxLength={48} /></label>
        <label className="text-sm space-y-1 block"><span className="text-gov-gray-500">Worker de DuckClaw (opcional)</span>
          <input className={INPUT} value={d.worker_id} onChange={(e) => set('worker_id', e.target.value)} /></label>
      </div>
      <JsonField label="Ajustes del bot (JSON libre)" hint="Modelo, personalidad, metas, herramientas permitidas… lo que lea tu runner."
        value={d.settings} onChange={(v) => set('settings', v)} />
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={d.enabled} onChange={(e) => set('enabled', e.target.checked)} /> Habilitado</label>
      <div className="flex gap-2">
        <button className={BTN} disabled={bad || saving} onClick={async () => { setSaving(true); try { await onSave(d); } finally { setSaving(false); } }}>
          {saving ? <Loader2 size={16} className="animate-spin" /> : null} Guardar
        </button>
        <button className={BTN} onClick={onCancel}>Cancelar</button>
      </div>
    </div>
  );
}

export default function WorldsView() {
  const [worlds, setWorlds] = useState<World[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingWorld, setEditingWorld] = useState<string | 'new' | null>(null);
  const [editingBot, setEditingBot] = useState<string | null>(null); // bot id, or `new:<worldId>`

  const load = useCallback(async () => {
    try {
      setWorlds((await worldsApi.list()).worlds);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo cargar Worlds');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => { if (document.visibilityState === 'visible') void load(); }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  // Writes are accepted by the queue and applied a moment later: reload after a short wait.
  const afterWrite = useCallback(async () => { await new Promise((r) => setTimeout(r, 700)); await load(); }, [load]);
  const run = async (fn: () => Promise<unknown>) => {
    try { await fn(); setEditingWorld(null); setEditingBot(null); await afterWrite(); } catch (e) { setError(e instanceof Error ? e.message : 'Error al guardar'); }
  };

  const saveWorld = (id: string | 'new') => (d: WorldDraft) => run(() => {
    const body = { name: d.name.trim(), kind: d.kind.trim() || 'generic', host: d.host.trim(), port: d.port ? Number(d.port) : null,
      config: (parseJsonObject(d.config) as { value: Record<string, unknown> }).value, enabled: d.enabled };
    return id === 'new' ? worldsApi.createWorld(body) : worldsApi.updateWorld(id, body);
  });
  const saveBot = (world: World, bot?: WorldBot) => (d: BotDraft) => run(() => {
    const body = { name: d.name.trim(), worker_id: d.worker_id.trim(), settings: (parseJsonObject(d.settings) as { value: Record<string, unknown> }).value, enabled: d.enabled };
    return bot ? worldsApi.updateBot(bot.id, body) : worldsApi.createBot(world.id, body);
  });

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black dark:text-dark-text flex items-center gap-2"><Globe size={28} /> Worlds</h1>
          <p className="text-sm text-gov-gray-500 mt-1 max-w-2xl">
            Registra los mundos que tú alojas (por ejemplo un servidor de Minecraft) y los bots que viven en ellos. DuckClaw solo guarda la configuración y muestra el
            estado que reporta tu runner: no aloja ni arranca nada, tú decides dónde y cómo corre.
          </p>
        </div>
        <div className="flex gap-2">
          <button className={BTN} onClick={() => void load()}><RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Actualizar</button>
          <button className={BTN} onClick={() => setEditingWorld('new')}><Plus size={16} /> Nuevo mundo</button>
        </div>
      </header>

      {error && <div className="border border-red-300 text-red-700 rounded-xl p-3 text-sm">{error}</div>}
      {editingWorld === 'new' && <WorldForm initial={worldDraftOf()} onSave={saveWorld('new')} onCancel={() => setEditingWorld(null)} />}

      {!loading && worlds.length === 0 && editingWorld !== 'new' && (
        <div className="border rounded-2xl p-8 text-center text-sm text-gov-gray-500 dark:border-dark-border">Aún no hay mundos. Crea el primero con «Nuevo mundo».</div>
      )}

      {worlds.map((w) => (
        <section key={w.id} className="border rounded-2xl p-4 space-y-3 dark:border-dark-border">
          {editingWorld === w.id ? (
            <WorldForm initial={worldDraftOf(w)} onSave={saveWorld(w.id)} onCancel={() => setEditingWorld(null)} />
          ) : (
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-xl font-bold dark:text-dark-text">{w.name} <span className="text-xs font-normal px-2 py-0.5 rounded-full bg-gov-gray-100 dark:bg-dark-surface">{w.kind}</span>
                  {!w.enabled && <span className="ml-2 text-xs text-gov-gray-500">(deshabilitado)</span>}</h2>
                <p className="text-sm text-gov-gray-500 font-mono">{w.host || 'sin host'}{w.port != null ? `:${w.port}` : ''}</p>
                {Object.keys(w.config).length > 0 && <pre className="text-xs text-gov-gray-500 mt-2 max-h-32 overflow-auto">{JSON.stringify(w.config, null, 2)}</pre>}
              </div>
              <div className="flex gap-2">
                <button className={BTN} onClick={() => setEditingWorld(w.id)}><Pencil size={16} /> Editar</button>
                <button className={BTN} onClick={() => { if (window.confirm(`¿Borrar el mundo «${w.name}» y sus bots?`)) void run(() => worldsApi.deleteWorld(w.id)); }}><Trash2 size={16} /> Borrar</button>
              </div>
            </div>
          )}

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold flex items-center gap-2"><Bot size={16} /> Bots ({w.bots.length})</h3>
              <button className={BTN} onClick={() => setEditingBot(`new:${w.id}`)}><Plus size={16} /> Nuevo bot</button>
            </div>
            {editingBot === `new:${w.id}` && <BotForm initial={botDraftOf()} onSave={saveBot(w)} onCancel={() => setEditingBot(null)} />}
            {w.bots.map((b) => editingBot === b.id ? (
              <BotForm key={b.id} initial={botDraftOf(b)} onSave={saveBot(w, b)} onCancel={() => setEditingBot(null)} />
            ) : (
              <div key={b.id} className="flex flex-wrap items-center justify-between gap-3 border rounded-xl px-3 py-2 dark:border-dark-border">
                <div>
                  <span className="font-medium dark:text-dark-text">{b.name}</span>{!b.enabled && <span className="ml-2 text-xs text-gov-gray-500">(deshabilitado)</span>}
                  {b.worker_id && <span className="ml-2 text-xs text-gov-gray-500">worker: {b.worker_id}</span>}
                  {b.status_detail && <p className="text-xs text-gov-gray-500">{b.status_detail}</p>}
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge bot={b} />
                  <button className={BTN} onClick={() => setEditingBot(b.id)}><Pencil size={14} /></button>
                  <button className={BTN} onClick={() => { if (window.confirm(`¿Borrar el bot «${b.name}»?`)) void run(() => worldsApi.deleteBot(b.id)); }}><Trash2 size={14} /></button>
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}

      <details className="border rounded-2xl p-4 text-sm dark:border-dark-border">
        <summary className="cursor-pointer font-semibold">Cómo se conecta tu runner</summary>
        <div className="mt-3 space-y-2 text-gov-gray-500">
          <p>Tu runner lee esta configuración y reporta su estado con la API del Gateway (servidor a servidor, con la clave de administración y el correo del dueño en <code>X-Duckclaw-Actor</code>):</p>
          <pre className="text-xs overflow-auto">{`GET  /api/v1/admin/worlds                 → mundos y bots con su configuración
POST /api/v1/admin/worlds/bots/status      {"bot_id": "...", "status": "online|starting|offline|error", "detail": "..."}`}</pre>
          <p>Un bot que deja de reportar durante ~90 s se muestra como <b>offline</b>. Las claves (OpenRouter, RCON…) no se guardan aquí: viven en el entorno de tu runner.</p>
        </div>
      </details>
    </div>
  );
}
