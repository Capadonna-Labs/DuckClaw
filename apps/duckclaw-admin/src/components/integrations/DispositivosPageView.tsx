'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { ExternalLink, Plug, Smartphone, Server } from 'lucide-react';
import { ViewChrome, type EmbeddedViewProps } from '@/components/admin/embeddedView';
import { DeviceStatusCard, type DeviceStatusTone } from '@/components/integrations/DeviceStatusCard';
import type { AndroidDeviceStatus } from '@/lib/androidAdbBff';
import { isGatewayHealthy } from '@/lib/healthLabels';
import { adminService } from '@/services/adminService';
import { useGatewayHealthStore } from '@/store/gatewayHealthStore';

const ADB_DEBUG_PORT_KEY = 'duckclaw:android-adb-debug-port';

function parseDebugPort(raw: string): number | null {
  const n = parseInt(raw.trim(), 10);
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

  const connectAdb = useCallback(async () => {
    const port = parseDebugPort(debugPortRef.current?.value ?? '');
    if (port == null) {
      setConnectMessage('Puerto inválido (1–65535)');
      return;
    }
    setConnectBusy(true);
    setConnectMessage(null);
    try {
      sessionStorage.setItem(ADB_DEBUG_PORT_KEY, String(port));
      const out = await adminService.runOps('android_adb_connect', { debug_port: port });
      let detail = out.stderr?.trim() || '';
      if (out.stdout) {
        try {
          const parsed = JSON.parse(out.stdout) as { host?: string; stdout?: string; stderr?: string };
          detail = parsed.stdout || parsed.stderr || parsed.host || detail;
        } catch {
          detail = out.stdout.trim() || detail;
        }
      }
      if (!out.ok) {
        throw new Error(detail || 'adb connect falló');
      }
      setConnectMessage(detail ? `Conectado: ${detail}` : 'ADB conectado');
      await loadAndroid();
    } catch (e) {
      setConnectMessage(e instanceof Error ? e.message : 'No se pudo conectar ADB');
    } finally {
      setConnectBusy(false);
    }
  }, [loadAndroid]);

  const gatewayOk = isGatewayHealthy(health);
  const pm2Rows = useMemo(() => {
    const names = ['DuckClaw-Gateway', 'DuckClaw-DB-Writer', 'DuckClaw-Heartbeat'];
    const byName = new Map((health?.pm2 ?? []).map((row) => [row.name, row]));
    return names.map((name) => byName.get(name) ?? { name, status: 'unknown' });
  }, [health?.pm2]);

  const androidFooter = (
    <>
      Grants y MCP en{' '}
      <Link href="/mcp/connectors" className="font-semibold text-gov-blue-700 dark:text-dark-cyan">
        MCP → conector Android Agent
      </Link>
      . Env: <code className="font-mono">ANDROID_ADB_HOST</code>,{' '}
      <code className="font-mono">ANDROID_ADB_DEBUG_PORT</code>,{' '}
      <code className="font-mono">ANDROID_MCP_PORT</code>,{' '}
      <code className="font-mono">ANDROID_MCP_COMMAND</code>.
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

        <p className="text-sm text-gov-gray-600 dark:text-dark-muted">
          Esta pestaña muestra telemetría del dispositivo (conexión ADB, modelo, batería). La
          configuración del conector MCP, grants por worker y arranque del servidor Android MCP viven
          en la pestaña MCP.
        </p>

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
              <div className="flex w-full flex-wrap items-end gap-2">
                <label className="flex min-w-[8rem] flex-col gap-0.5 text-xs">
                  <span className="font-semibold text-gov-gray-500 dark:text-dark-muted">
                    Puerto debug inalámbrico
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
                    placeholder="Puerto del teléfono"
                    defaultValue=""
                    onInput={(e) => {
                      e.currentTarget.value = e.currentTarget.value.replace(/\D/g, '');
                    }}
                    className="rounded-lg border border-gov-gray-200 px-2 py-1.5 font-mono text-sm dark:border-dark-border dark:bg-dark-bg"
                  />
                </label>
                <button
                  type="button"
                  disabled={connectBusy || androidLoading}
                  onClick={() => void connectAdb()}
                  className="inline-flex items-center gap-1 rounded-lg bg-gov-blue-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50 dark:bg-dark-cyan dark:text-dark-bg"
                >
                  <Plug size={12} className={connectBusy ? 'animate-pulse' : ''} />
                  {connectBusy ? 'Conectando…' : 'Conectar ADB'}
                </button>
              </div>
            }
            footer={androidFooter}
          >
            {connectMessage ? (
              <p
                className={`rounded-lg px-3 py-2 text-xs ${
                  connectMessage.startsWith('Conectado')
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
            subtitle="Gateway, Redis y procesos PM2 core"
            tone={vpsTone(gatewayOk, recovering)}
            statusLabel={
              recovering ? 'Recuperando…' : gatewayOk ? 'Saludable' : healthError ? 'Offline' : '—'
            }
            onRefresh={() => void refreshHealth(true)}
            refreshing={recovering}
            footer={
              <>
                Detalle en{' '}
                <Link href="/overview" className="inline-flex items-center gap-1 font-semibold text-gov-blue-700 dark:text-dark-cyan">
                  Overview
                  <ExternalLink size={12} />
                </Link>
              </>
            }
          >
            <div className="flex items-start gap-3 text-sm text-gov-gray-700 dark:text-dark-muted">
              <Server size={18} className="mt-0.5 shrink-0 opacity-70" />
              <dl className="grid w-full gap-1 text-xs sm:text-sm">
                <div className="flex gap-2">
                  <dt className="font-semibold text-gov-gray-500">Gateway</dt>
                  <dd>{gatewayOk ? 'OK' : healthError ? 'error' : '—'}</dd>
                </div>
                <div className="flex gap-2">
                  <dt className="font-semibold text-gov-gray-500">Redis</dt>
                  <dd>
                    {health?.redis === true ? 'OK' : health?.redis === false ? 'offline' : '—'}
                  </dd>
                </div>
                {pm2Rows.map((row) => (
                  <div key={row.name} className="flex gap-2">
                    <dt className="font-semibold text-gov-gray-500">{row.name}</dt>
                    <dd>{row.status || '—'}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </DeviceStatusCard>
        </div>
      </div>
    </ViewChrome>
  );
}
