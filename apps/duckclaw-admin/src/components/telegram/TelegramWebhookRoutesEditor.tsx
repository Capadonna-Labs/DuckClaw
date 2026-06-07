'use client';

import { useCallback, useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';
import SettingsSection from '@/components/settings/SettingsSection';
import { MessageSquare, Plus, Trash2 } from 'lucide-react';

type RouteRow = {
  bot: string;
  path: string;
  worker_id: string;
  tenant_id: string;
  vault_env_var: string;
  token: string;
  token_masked?: string;
};

const DEFAULT_PATH = (bot: string) =>
  `/api/v1/telegram/${bot.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '')}`;

export function TelegramWebhookRoutesEditor({ canWrite }: { canWrite: boolean }) {
  const [rows, setRows] = useState<RouteRow[]>([]);
  const [knownBots, setKnownBots] = useState<string[]>([]);
  const [format, setFormat] = useState<string>('empty');
  const [source, setSource] = useState<string>('default');
  const [parseError, setParseError] = useState<string | null>(null);
  const [routesMsg, setRoutesMsg] = useState<string | null>(null);
  const [routesError, setRoutesError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const loadRoutes = useCallback(() => {
    adminService
      .getTelegramRoutes()
      .then((r) => {
        setFormat(r.format);
        setSource(r.source ?? 'default');
        setKnownBots(r.known_bots ?? []);
        setParseError(r.parse_error ?? null);
        setRows(
          (r.routes ?? []).map((row) => ({
            bot: row.bot,
            path: row.path,
            worker_id: row.worker_id || row.bot,
            tenant_id: row.tenant_id || 'default',
            vault_env_var: row.vault_env_var || '',
            token: '',
            token_masked: row.token_masked,
          }))
        );
      })
      .catch((e) => setRoutesError(e instanceof Error ? e.message : 'Error cargando rutas'));
  }, []);

  useEffect(() => {
    loadRoutes();
  }, [loadRoutes]);

  const updateRow = (index: number, patch: Partial<RouteRow>) => {
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  };

  const addRow = () => {
    const bot = knownBots.find((b) => !rows.some((r) => r.bot === b)) ?? '';
    setRows((prev) => [
      ...prev,
      {
        bot,
        path: bot ? DEFAULT_PATH(bot) : '/api/v1/telegram/',
        worker_id: bot || 'default',
        tenant_id: 'default',
        vault_env_var: '',
        token: '',
      },
    ]);
  };

  const removeRow = (index: number) => {
    setRows((prev) => prev.filter((_, i) => i !== index));
  };

  const saveRoutes = async () => {
    if (!canWrite) return;
    setSaving(true);
    setRoutesError(null);
    setRoutesMsg(null);
    try {
      const payload = rows.map((r) => ({
        bot: r.bot.trim().toLowerCase(),
        path: r.path.trim(),
        worker_id: r.worker_id.trim(),
        tenant_id: r.tenant_id.trim(),
        ...(r.vault_env_var.trim() ? { vault_env_var: r.vault_env_var.trim() } : {}),
        ...(r.token.trim() ? { token: r.token.trim() } : {}),
      }));
      const res = await adminService.putTelegramRoutes(payload);
      setRoutesMsg(
        `Guardado en DuckDB (${res.route_count} rutas). ${res.restart_hint ?? 'Reinicia DuckClaw-Gateway para registrar rutas dinámicas.'}`
      );
      loadRoutes();
    } catch (e) {
      setRoutesError(e instanceof Error ? e.message : 'Error guardando rutas');
    } finally {
      setSaving(false);
    }
  };

  const jsonMode = format === 'json';

  return (
    <SettingsSection
      titulo="Rutas webhook"
      descripcion="Runtime Settings DB-first con .env como fallback bootstrap"
      icono={<MessageSquare size={22} />}
    >
      <div className="space-y-4">
        <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
          Fuente efectiva: <span className="font-mono">{source}</span> · setting{' '}
          <span className="font-mono">telegram.webhook_routes</span>
        </p>
        {parseError && (
          <p className="text-sm text-red-600 dark:text-red-400">
            Error al parsear rutas Telegram: {parseError}
          </p>
        )}
        {jsonMode && (
          <p className="text-sm text-amber-800 dark:text-amber-200 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 rounded-xl p-3">
            El valor actual viene en formato JSON multiplex legacy. Migra a formato compacto desde Runtime Settings o
            migra a formato compacto manualmente.
          </p>
        )}

        {!jsonMode && (
          <>
            <div className="overflow-x-auto rounded-2xl border dark:border-dark-border">
              <table className="w-full text-sm">
                <thead className="bg-gov-gray-50 dark:bg-dark-bg text-left text-gov-gray-500">
                  <tr>
                    <th className="px-3 py-2 font-mono text-xs">bot</th>
                    <th className="px-3 py-2 font-mono text-xs">token</th>
                    <th className="px-3 py-2 font-mono text-xs">path</th>
                    <th className="px-3 py-2 font-mono text-xs">worker</th>
                    <th className="px-3 py-2 font-mono text-xs">tenant</th>
                    <th className="px-3 py-2 font-mono text-xs">vault env</th>
                    {canWrite && <th className="px-3 py-2 w-10" />}
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 && (
                    <tr>
                      <td colSpan={canWrite ? 7 : 6} className="px-4 py-6 text-center text-gov-gray-500">
                        Sin rutas. Añade una fila o conserva el fallback bootstrap.
                      </td>
                    </tr>
                  )}
                  {rows.map((row, i) => (
                    <tr key={`${row.bot}-${i}`} className="border-t dark:border-dark-border">
                      <td className="px-2 py-2 align-top">
                        {canWrite ? (
                          <input
                            list={`telegram-bots-${i}`}
                            value={row.bot}
                            onChange={(e) => {
                              const bot = e.target.value.toLowerCase();
                              updateRow(i, {
                                bot,
                                path: row.path || DEFAULT_PATH(bot),
                              });
                            }}
                            className="w-full min-w-[7rem] px-2 py-1.5 font-mono text-xs border rounded-lg dark:border-dark-border dark:bg-dark-bg"
                            placeholder="my-bot"
                          />
                        ) : (
                          <span className="font-mono text-xs px-2">{row.bot}</span>
                        )}
                        {canWrite && knownBots.length > 0 && (
                          <datalist id={`telegram-bots-${i}`}>
                            {knownBots.map((b) => (
                              <option key={b} value={b} />
                            ))}
                          </datalist>
                        )}
                      </td>
                      <td className="px-2 py-2 align-top">
                        {canWrite ? (
                          <input
                            type="password"
                            value={row.token}
                            onChange={(e) => updateRow(i, { token: e.target.value })}
                            placeholder={row.token_masked || 'Token (vacío = sin cambio)'}
                            className="w-full min-w-[10rem] px-2 py-1.5 font-mono text-xs border rounded-lg dark:border-dark-border dark:bg-dark-bg"
                            autoComplete="off"
                          />
                        ) : (
                          <span className="font-mono text-xs text-gov-gray-500 px-2">
                            {row.token_masked || '—'}
                          </span>
                        )}
                      </td>
                      <td className="px-2 py-2 align-top">
                        {canWrite ? (
                          <input
                            value={row.path}
                            onChange={(e) => updateRow(i, { path: e.target.value })}
                            className="w-full min-w-[14rem] px-2 py-1.5 font-mono text-xs border rounded-lg dark:border-dark-border dark:bg-dark-bg"
                            placeholder="/api/v1/telegram/my-bot"
                          />
                        ) : (
                          <span className="font-mono text-xs px-2 break-all">{row.path}</span>
                        )}
                      </td>
                      <td className="px-2 py-2 align-top">
                        {canWrite ? (
                          <input
                            value={row.worker_id}
                            onChange={(e) => updateRow(i, { worker_id: e.target.value })}
                            className="w-full min-w-[8rem] px-2 py-1.5 font-mono text-xs border rounded-lg dark:border-dark-border dark:bg-dark-bg"
                            placeholder="Worker-A"
                          />
                        ) : (
                          <span className="font-mono text-xs px-2">{row.worker_id}</span>
                        )}
                      </td>
                      <td className="px-2 py-2 align-top">
                        {canWrite ? (
                          <input
                            value={row.tenant_id}
                            onChange={(e) => updateRow(i, { tenant_id: e.target.value })}
                            className="w-full min-w-[8rem] px-2 py-1.5 font-mono text-xs border rounded-lg dark:border-dark-border dark:bg-dark-bg"
                            placeholder="default"
                          />
                        ) : (
                          <span className="font-mono text-xs px-2">{row.tenant_id}</span>
                        )}
                      </td>
                      <td className="px-2 py-2 align-top">
                        {canWrite ? (
                          <input
                            value={row.vault_env_var}
                            onChange={(e) => updateRow(i, { vault_env_var: e.target.value })}
                            className="w-full min-w-[10rem] px-2 py-1.5 font-mono text-xs border rounded-lg dark:border-dark-border dark:bg-dark-bg"
                            placeholder="DUCKCLAW_AXIS_DB_PATH"
                          />
                        ) : (
                          <span className="font-mono text-xs px-2">{row.vault_env_var || '—'}</span>
                        )}
                      </td>
                      {canWrite && (
                        <td className="px-2 py-2 align-top">
                          <button
                            type="button"
                            onClick={() => removeRow(i)}
                            className="text-red-600 hover:text-red-800 p-1"
                            aria-label="Quitar ruta"
                          >
                            <Trash2 size={16} />
                          </button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {canWrite && (
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={addRow}
                  className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-bold border rounded-xl dark:border-dark-border hover:border-gov-blue-500"
                >
                  <Plus size={14} />
                  Añadir ruta
                </button>
                <button
                  type="button"
                  onClick={saveRoutes}
                  disabled={saving || rows.length === 0}
                  className="px-4 py-2 bg-gov-blue-700 text-white rounded-xl text-sm font-bold disabled:opacity-50"
                >
                  {saving ? 'Guardando…' : 'Guardar rutas en DuckDB'}
                </button>
                <button
                  type="button"
                  onClick={loadRoutes}
                  className="px-3 py-2 text-xs border rounded-xl dark:border-dark-border"
                >
                  Descartar cambios
                </button>
              </div>
            )}
          </>
        )}

        {routesError && <p className="text-red-600 text-sm">{routesError}</p>}
        {routesMsg && <p className="text-green-700 dark:text-green-400 text-sm">{routesMsg}</p>}

        <p className="text-xs text-gov-gray-500">
          Formato: <code className="font-mono">bot:token:/api/v1/telegram/…</code> separado por comas.
          Los tokens son write-only: si el campo queda vacío, se conserva el token efectivo actual.
        </p>
      </div>
    </SettingsSection>
  );
}
