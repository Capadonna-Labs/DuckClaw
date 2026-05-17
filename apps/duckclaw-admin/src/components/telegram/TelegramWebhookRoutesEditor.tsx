'use client';

import { useCallback, useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';
import SettingsSection from '@/components/settings/SettingsSection';
import { MessageSquare, Plus, Trash2 } from 'lucide-react';

type RouteRow = {
  bot: string;
  path: string;
  token: string;
  token_masked?: string;
};

const DEFAULT_PATH = (bot: string) =>
  `/api/v1/telegram/${bot.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '')}`;

export function TelegramWebhookRoutesEditor({ canWrite }: { canWrite: boolean }) {
  const [rows, setRows] = useState<RouteRow[]>([]);
  const [knownBots, setKnownBots] = useState<string[]>([]);
  const [format, setFormat] = useState<string>('empty');
  const [parseError, setParseError] = useState<string | null>(null);
  const [routesMsg, setRoutesMsg] = useState<string | null>(null);
  const [routesError, setRoutesError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const loadRoutes = useCallback(() => {
    adminService
      .getTelegramRoutes()
      .then((r) => {
        setFormat(r.format);
        setKnownBots(r.known_bots ?? []);
        setParseError(r.parse_error ?? null);
        setRows(
          (r.routes ?? []).map((row) => ({
            bot: row.bot,
            path: row.path,
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
      { bot, path: bot ? DEFAULT_PATH(bot) : '/api/v1/telegram/', token: '' },
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
        ...(r.token.trim() ? { token: r.token.trim() } : {}),
      }));
      const res = await adminService.putTelegramRoutes(payload);
      setRoutesMsg(
        `Guardado (${res.route_count} rutas). Reinicia el gateway: ${res.restart_hint ?? 'pm2 restart DuckClaw-Gateway --update-env'}`
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
      descripcion="DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES (formato compacto en .env)"
      icono={<MessageSquare size={22} />}
    >
      <div className="space-y-4">
        {parseError && (
          <p className="text-sm text-red-600 dark:text-red-400">
            Error al parsear .env: {parseError}
          </p>
        )}
        {jsonMode && (
          <p className="text-sm text-amber-800 dark:text-amber-200 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 rounded-xl p-3">
            El valor actual es JSON multiplex. Edítalo en <code className="text-xs">.env</code> o
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
                    {canWrite && <th className="px-3 py-2 w-10" />}
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 && (
                    <tr>
                      <td colSpan={canWrite ? 4 : 3} className="px-4 py-6 text-center text-gov-gray-500">
                        Sin rutas. Añade una fila o configura el .env.
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
                            placeholder="finanz"
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
                            placeholder="/api/v1/telegram/finanz"
                          />
                        ) : (
                          <span className="font-mono text-xs px-2 break-all">{row.path}</span>
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
                  {saving ? 'Guardando…' : 'Guardar rutas en .env'}
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
          Tras guardar, reinicia <strong>DuckClaw-Gateway</strong> y registra webhooks si cambió la URL
          pública.
        </p>
      </div>
    </SettingsSection>
  );
}
