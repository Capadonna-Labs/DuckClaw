'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { ExternalLink, Plug, Smartphone, Server } from 'lucide-react';
import { ViewChrome, type EmbeddedViewProps } from '@/components/admin/embeddedView';
import { DeviceStatusCard, type DeviceStatusTone } from '@/components/integrations/DeviceStatusCard';
import type { AndroidDeviceStatus } from '@/lib/androidAdbBff';
import { isGatewayHealthy } from '@/lib/healthLabels';
import { adminService } from '@/services/adminService';
import { useGatewayHealthStore } from '@/store/gatewayHealthStore';

const ADB_DEBUG_PORT_KEY = 'duckclaw:android-adb-debug-port';
const ADB_PAIR_PORT_KEY = 'duckclaw:android-adb-pair-port';

function parsePort(raw: string): number | null {
  const text = raw.trim();
  if (!text) return null;
  const fromHost = text.match(/:(\d+)\s*$/);
  const n = parseInt(fromHost ? fromHost[1] : text.replace(/\D/g, ''), 10);
  if (!Number.isFinite(n) || n < 1 || n > 65535) return null;
  return n;
}

function androidTone(status: AndroidDeviceStatus | null): DeviceStatusTone {
  if (!status) return 'neutral';
  if (status.adb_connected && status.mcp_reachable) return 'ok';
  if (status.adb_connected || status.mcp_reachable) return 'warn';
  return 'bad';
}

function androidStatusLabel(status: AndroidDeviceStatus | null): string {
  if (!status) return 'Comprobando…';
  if (!status.adb_available) return 'ADB no disponible';
  if (!status.adb_connected) return 'ADB offline';
  if (!status.mcp_reachable) return 'MCP offline';
  return 'Conectado';
}

function vpsTone(healthy: boolean | null, recovering: boolean): DeviceStatusTone {
  if (recovering) return 'warn';
  if (healthy === true) return 'ok';
  if (healthy === false) return 'bad';
  return 'neutral';
}

export default function DispositivosPageView({ embedded = false }: EmbeddedViewProps) {
  const [android, setAndroid] = useState<AndroidDeviceStatus | null>(null);
  const [androidError, setAndroidError] = useState<string | null>(null);
  const [androidLoading, setAndroidLoading] = useState(true);
  const debugPortRef = useRef<HTMLInputElement>(null);
  const pairPortRef = useRef<HTMLInputElement>(null);
  const pairCodeRef = useRef<HTMLInputElement>(null);
  const [connectBusy, setConnectBusy] = useState(false);
  const [connectMessage, setConnectMessage] = useState<string | null>(null);
  const { data: health, error: healthError, recovering, refresh: refreshHealth } =
    useGatewayHealthStore();

  const loadAndroid = useCallback(async () => {
    setAndroidLoading(true);
    setAndroidError(null);
    try {
      const res = await fetch('/api/admin/devices/android-status', { cache: 'no-store' });
      const payload = (await res.json()) as AndroidDeviceStatus & { detail?: string };
      if (!res.ok) {
        throw new Error(typeof payload.detail === 'string' ? payload.detail : `HTTP ${res.status}`);
      }
      setAndroid(payload);
    } catch (e) {
      setAndroidError(e instanceof Error ? e.message : 'No se pudo leer estado Android');
    } finally {
      setAndroidLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAndroid();
    void refreshHealth();
  }, [loadAndroid, refreshHealth]);

  useEffect(() => {
    const input = debugPortRef.current;
    if (!input || input.value.trim()) return;
    const stored = sessionStorage.getItem(ADB_DEBUG_PORT_KEY);
    if (stored) input.value = stored;
    const pairStored = sessionStorage.getItem(ADB_PAIR_PORT_KEY);
    if (pairStored && pairPortRef.current && !pairPortRef.current.value.trim()) {
      pairPortRef.current.value = pairStored;
    }
  }, []);

  useEffect(() => {
    const input = debugPortRef.current;
    if (!input || input.value.trim()) return;
    const fromServer = android?.adb_debug_port?.trim();
    if (fromServer) input.value = fromServer;
  }, [android?.adb_debug_port]);

  const connectAdb = useCallback(async () => {
    const port =
      parsePort(debugPortRef.current?.value ?? '') ??
      parsePort(android?.adb_debug_port ?? '');
    if (port == null) {
      setConnectMessage(
        'Falta puerto debug: en el teléfono cierra el diálogo de pair y copia el número después de los dos puntos (ej. 42961).',
      );
      return;
    }
    const pairPortRaw = pairPortRef.current?.value ?? '';
    const pairCodeRaw = (pairCodeRef.current?.value ?? '').trim();
    const pairPort = pairPortRaw.trim() ? parsePort(pairPortRaw) : null;
    if (pairPortRaw.trim() && pairPort == null) {
      setConnectMessage('Puerto pair inválido (1–65535)');
      return;
    }
    if ((pairPort != null && !pairCodeRaw) || (pairCodeRaw && pairPort == null)) {
      setConnectMessage('Emparejamiento requiere puerto pair y código de 6 dígitos');
      return;
    }
    setConnectBusy(true);
    setConnectMessage(null);
    try {
      sessionStorage.setItem(ADB_DEBUG_PORT_KEY, String(port));
      if (pairPort != null) sessionStorage.setItem(ADB_PAIR_PORT_KEY, String(pairPort));
      const params: Record<string, string | number> = { debug_port: port };
      if (pairPort != null) params.pair_port = pairPort;
      if (pairCodeRaw) params.pair_code = pairCodeRaw;
      const out = await adminService.runOps('android_adb_connect', params);
      let detail = out.stderr?.trim() || '';
      let envUpdated: string[] | undefined;
      let hint = '';
      if (out.stdout) {
        try {
          const parsed = JSON.parse(out.stdout) as {
            host?: string;
            stdout?: string;
            stderr?: string;
            hint?: string;
            paired?: boolean;
            env_updated?: string[];
          };
          detail = parsed.stdout || parsed.stderr || parsed.host || detail;
          envUpdated = parsed.env_updated;
          hint = parsed.hint || '';
          if (parsed.paired) {
            detail = `Emparejado. ${detail}`.trim();
            if (pairCodeRef.current) pairCodeRef.current.value = '';
          }
        } catch {
          detail = out.stdout.trim() || detail;
        }
      }
      if (!out.ok) {
        await loadAndroid();
        throw new Error(
          [detail || 'adb connect falló', hint, envUpdated?.length ? `(env: ${envUpdated.join(', ')})` : '']
            .filter(Boolean)
            .join(' '),
        );
      }
      const savedKeys = envUpdated?.length
        ? ` · .env: ${envUpdated.join(', ')}`
        : ' · .env actualizado';
      setConnectMessage(detail ? `${detail}${savedKeys}` : `ADB conectado${savedKeys}`);
      await loadAndroid();
    } catch (e) {
      setConnectMessage(e instanceof Error ? e.message : 'No se pudo conectar ADB');
    } finally {
      setConnectBusy(false);
    }
  }, [android?.adb_debug_port, loadAndroid]);

  const gatewayOk = health ? isGatewayHealthy(health.status) : null;

  const androidFooter = (
    <>
      Grants y MCP en{' '}
      <Link href="/mcp/connectors" className="font-semibold text-gov-blue-700 dark:text-dark-cyan">
        MCP → Android Agent
      </Link>
      .
    </>
  );

  return (
    <ViewChrome embedded={embedded}>
      <div className="space-y-4">
        {!embedded && (
          <header className="border-b border-gov-gray-200 pb-4 dark:border-dark-border">
            <h1 className="text-2xl font-bold text-gov-gray-900 dark:text-dark-text">Dispositivos</h1>
            <p className="mt-1 text-sm text-gov-gray-600 dark:text-dark-muted">
              Monitoreo físico Android (ADB) e infraestructura del host
            </p>
          </header>
        )}

        {androidError ? (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-400">
            {androidError}
          </p>
        ) : null}

        <div className="grid gap-4 lg:grid-cols-2">
          <DeviceStatusCard
            title="Android físico"
            subtitle={android?.mcp_url || 'ADB + MCP local'}
            tone={androidTone(android)}
            statusLabel={androidLoading ? 'Comprobando…' : androidStatusLabel(android)}
            onRefresh={() => void loadAndroid()}
            refreshing={androidLoading}
            actions={
              <div className="space-y-3">
                <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
                  Depuración inalámbrica: puerto pair + código, luego puerto debug.
                </p>
                <div className="grid gap-2 sm:grid-cols-3">
                  <label className="block text-xs">
                    <span className="mb-1 block font-semibold text-gov-gray-500 dark:text-dark-muted">
                      Puerto pair
                    </span>
                    <input
                      ref={pairPortRef}
                      type="text"
                      inputMode="numeric"
                      name="adb-wireless-pair-port"
                      autoComplete="off"
                      placeholder="ej. 42871"
                      defaultValue=""
                      className="w-full rounded-lg border border-gov-gray-200 px-3 py-2 font-mono text-sm dark:border-dark-border dark:bg-dark-bg"
                    />
                  </label>
                  <label className="block text-xs">
                    <span className="mb-1 block font-semibold text-gov-gray-500 dark:text-dark-muted">
                      Código pair
                    </span>
                    <input
                      ref={pairCodeRef}
                      type="text"
                      inputMode="numeric"
                      name="adb-wireless-pair-code"
                      autoComplete="off"
                      placeholder="6 dígitos"
                      maxLength={6}
                      defaultValue=""
                      onInput={(e) => {
                        e.currentTarget.value = e.currentTarget.value.replace(/\D/g, '').slice(0, 6);
                      }}
                      className="w-full rounded-lg border border-gov-gray-200 px-3 py-2 font-mono text-sm tracking-widest dark:border-dark-border dark:bg-dark-bg"
                    />
                  </label>
                  <label className="block text-xs">
                    <span className="mb-1 block font-semibold text-gov-gray-500 dark:text-dark-muted">
                      Puerto debug
                    </span>
                    <input
                      ref={debugPortRef}
                      type="text"
                      inputMode="numeric"
                      pattern="[0-9]*"
                      name="adb-wireless-debug-port"
                      autoComplete="off"
                      autoCorrect="off"
                      spellCheck={false}
                      placeholder="ej. 42961"
                      defaultValue=""
                      className="w-full rounded-lg border border-gov-gray-200 px-3 py-2 font-mono text-sm dark:border-dark-border dark:bg-dark-bg"
                    />
                  </label>
                </div>
                <button
                  type="button"
                  disabled={connectBusy || androidLoading}
                  onClick={() => void connectAdb()}
                  className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-gov-blue-700 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50 sm:w-auto dark:bg-dark-cyan dark:text-dark-bg"
                >
                  <Plug size={14} className={connectBusy ? 'animate-pulse' : ''} />
                  {connectBusy ? 'Conectando…' : 'Emparejar y conectar'}
                </button>
              </div>
            }
            footer={androidFooter}
          >
            {connectMessage ? (
              <p
                className={`rounded-lg px-3 py-2 text-xs ${
                  /^(already )?connected to\b/i.test(connectMessage.trim()) ||
                  connectMessage.startsWith('Conectado') ||
                  connectMessage.startsWith('Emparejado') ||
                  connectMessage.startsWith('ADB conectado')
                    ? 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200'
                    : 'bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-100'
                }`}
              >
                {connectMessage}
              </p>
            ) : null}
            <div className="flex items-start gap-3 text-sm text-gov-gray-700 dark:text-dark-muted">
              <Smartphone size={18} className="mt-0.5 shrink-0 opacity-70" />
              <dl className="grid gap-1 text-xs sm:text-sm">
                <div className="flex gap-2">
                  <dt className="font-semibold text-gov-gray-500">ADB host</dt>
                  <dd>{android?.adb_host || '—'}</dd>
                </div>
                <div className="flex gap-2">
                  <dt className="font-semibold text-gov-gray-500">Puerto debug (servidor)</dt>
                  <dd>{android?.adb_debug_port || '—'}</dd>
                </div>
                <div className="flex gap-2">
                  <dt className="font-semibold text-gov-gray-500">Dispositivo</dt>
                  <dd>
                    {android?.device
                      ? `${android.device.model || android.device.serial || '—'} (${android.device.state})`
                      : 'Sin dispositivo'}
                  </dd>
                </div>
                <div className="flex gap-2">
                  <dt className="font-semibold text-gov-gray-500">Batería</dt>
                  <dd>
                    {android?.battery?.level_pct != null
                      ? `${android.battery.level_pct}%${
                          android.battery.charging != null
                            ? android.battery.charging
                              ? ' · cargando'
                              : ' · descargando'
                            : ''
                        }`
                      : '—'}
                  </dd>
                </div>
                <div className="flex gap-2">
                  <dt className="font-semibold text-gov-gray-500">MCP</dt>
                  <dd>{android?.mcp_reachable ? 'reachable' : android?.mcp_error || 'offline'}</dd>
                </div>
                <div className="flex gap-2">
                  <dt className="font-semibold text-gov-gray-500">Leído</dt>
                  <dd>{android?.read_at ? new Date(android.read_at).toLocaleString() : '—'}</dd>
                </div>
              </dl>
            </div>
          </DeviceStatusCard>

          <DeviceStatusCard
            title="Host gateway"
            subtitle="Estado básico del stack"
            tone={vpsTone(gatewayOk, recovering)}
            statusLabel={
              recovering ? 'Recuperando…' : gatewayOk ? 'Saludable' : healthError ? 'Offline' : '—'
            }
            onRefresh={() => void refreshHealth(true)}
            refreshing={recovering}
            footer={
              <>
                Detalle en{' '}
                <Link
                  href="/overview"
                  className="inline-flex items-center gap-1 font-semibold text-gov-blue-700 dark:text-dark-cyan"
                >
                  Overview
                  <ExternalLink size={12} />
                </Link>
              </>
            }
          >
            <div className="flex items-start gap-3 text-sm text-gov-gray-700 dark:text-dark-muted">
              <Server size={18} className="mt-0.5 shrink-0 opacity-70" />
              <dl className="grid gap-1.5 text-sm">
                <div className="flex flex-wrap gap-x-2">
                  <dt className="min-w-[7rem] font-semibold text-gov-gray-500">Gateway</dt>
                  <dd>{gatewayOk ? 'OK' : healthError ? 'error' : health?.status || '—'}</dd>
                </div>
                <div className="flex flex-wrap gap-x-2">
                  <dt className="min-w-[7rem] font-semibold text-gov-gray-500">Redis</dt>
                  <dd>
                    {health?.redis === true ? 'OK' : health?.redis === false ? 'offline' : '—'}
                  </dd>
                </div>
                <div className="flex flex-wrap gap-x-2">
                  <dt className="min-w-[7rem] font-semibold text-gov-gray-500">Workers</dt>
                  <dd>{health?.workers_count ?? '—'}</dd>
                </div>
              </dl>
            </div>
          </DeviceStatusCard>
        </div>
      </div>
    </ViewChrome>
  );
}
