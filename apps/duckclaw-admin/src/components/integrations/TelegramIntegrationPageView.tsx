'use client';

import { useState } from 'react';
import Link from 'next/link';
import SettingsSection from '@/components/settings/SettingsSection';
import { ViewChrome, type EmbeddedViewProps } from '@/components/admin/embeddedView';
import { TelegramUsersPanel } from '@/components/access/TelegramUsersPanel';
import { TelegramWebhookRoutesEditor } from '@/components/telegram/TelegramWebhookRoutesEditor';
import { useAuthStore } from '@/store/authStore';
import { adminService } from '@/services/adminService';
import { formatOpsOutput } from '@/lib/formatOpsOutput';
import { Database, Globe, Users } from 'lucide-react';

export default function TelegramIntegrationPageView({ embedded = false }: EmbeddedViewProps) {
  const { usuario } = useAuthStore();
  const canWrite = usuario?.rol === 'admin';
  const [tenantId, setTenantId] = useState('default');
  const [ingressRunning, setIngressRunning] = useState(false);
  const [ingressOutput, setIngressOutput] = useState<string | null>(null);
  const [ingressError, setIngressError] = useState<string | null>(null);

  const activateIngress = async () => {
    if (!canWrite) return;
    setIngressRunning(true);
    setIngressError(null);
    setIngressOutput(null);
    try {
      const r = await adminService.runOps('start_telegram_ingress');
      setIngressOutput(
        formatOpsOutput({
          ok: r.ok,
          exit_code: r.exit_code,
          stdout: r.stdout,
          stderr: r.stderr,
          executed_via: r.executed_via,
          op_id: 'start_telegram_ingress',
        })
      );
      if (!r.ok) {
        setIngressError('No se pudo activar el ingress Telegram. Revisa tokens y rutas webhook.');
      }
    } catch (e) {
      setIngressError(e instanceof Error ? e.message : 'Error activando ingress');
    } finally {
      setIngressRunning(false);
    }
  };

  return (
    <ViewChrome embedded={embedded}>
      {!embedded && (
        <header>
          <h1 className="text-3xl font-black dark:text-dark-text">Telegram</h1>
          <p className="text-sm text-gov-gray-500 dark:text-dark-muted mt-1">
            Canal opcional — la consola web es el flujo principal (DB-first)
          </p>
        </header>
      )}

      <section className="rounded-2xl border border-amber-200 bg-amber-50/80 p-4 text-sm text-amber-950 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-100">
        <p className="font-bold">Integración avanzada, no requerida para empezar</p>
        <p className="mt-1 text-xs text-amber-900/90 dark:text-amber-100/90">
          Usa Playground y <Link href="/administracion?tab=acceso" className="underline font-semibold">Usuarios consola</Link>{' '}
          para operar sin bot. Esta sección solo aplica si expones DuckClaw por Telegram.
        </p>
      </section>

      <SettingsSection
        titulo="Configuración Telegram"
        descripcion="DB-first para rutas webhook; .env solo como fallback bootstrap si DuckDB aún no tiene rutas."
        icono={<Database size={22} />}
      >
        <div className="space-y-2 text-sm text-gov-gray-600 dark:text-dark-muted">
          <p>
            Las rutas webhook y sus tokens se guardan en{' '}
            <code className="font-mono text-xs">admin_runtime_settings</code> como{' '}
            <code className="font-mono text-xs">telegram.webhook_routes</code>.
          </p>
          <p>
            Los tokens son write-only desde la UI. Si aún no hay valor en DuckDB, el Gateway usa
            el fallback bootstrap compatible de <code className="font-mono text-xs">.env</code>.
          </p>
        </div>
      </SettingsSection>

      <SettingsSection
        titulo="Usuarios autorizados del bot"
        descripcion="Quién puede hablar con el bot (Telegram Guard)"
        icono={<Users size={22} />}
      >
        <p className="text-sm text-gov-gray-600 dark:text-dark-muted mb-4">
          Lista de <strong>user_id</strong> de Telegram permitidos por tenant. Es independiente del
          login de la consola web. También puedes gestionarla con{' '}
          <code className="font-mono text-xs">/team</code> dentro del bot.
        </p>
        <TelegramUsersPanel tenantId={tenantId} onTenantIdChange={setTenantId} />
      </SettingsSection>

      <TelegramWebhookRoutesEditor canWrite={canWrite} />

      <SettingsSection
        titulo="Ingress webhook (Tailscale + setWebhook)"
        descripcion="Paso final de la integración. No forma parte del arranque core de la plataforma."
        icono={<Globe size={22} />}
      >
        <p className="text-sm text-gov-gray-600 dark:text-dark-muted mb-4">
          Activa Funnel/Tailscale y registra webhooks en Bot API. Ejecuta esto después de guardar rutas arriba.
        </p>
        {canWrite ? (
          <button
            type="button"
            onClick={() => void activateIngress()}
            disabled={ingressRunning}
            className="rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60 dark:bg-dark-cyan dark:text-dark-bg"
          >
            {ingressRunning ? 'Activando…' : 'Activar ingress Telegram'}
          </button>
        ) : (
          <p className="text-xs text-gov-gray-500">Solo administradores pueden activar ingress.</p>
        )}
        {ingressError && (
          <p className="mt-3 text-sm text-red-600 dark:text-red-400">{ingressError}</p>
        )}
        {ingressOutput && (
          <pre className="mt-3 max-h-48 overflow-auto rounded-xl bg-gov-gray-900 p-3 text-xs text-gov-gray-100 whitespace-pre-wrap">
            {ingressOutput}
          </pre>
        )}
      </SettingsSection>
    </ViewChrome>
  );
}
