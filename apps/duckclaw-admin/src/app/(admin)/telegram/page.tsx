'use client';

import { useState } from 'react';
import Link from 'next/link';
import SettingsSection from '@/components/settings/SettingsSection';
import { PageShell } from '@/components/admin/PageShell';
import { TelegramUsersPanel } from '@/components/access/TelegramUsersPanel';
import { TelegramWebhookRoutesEditor } from '@/components/telegram/TelegramWebhookRoutesEditor';
import { useAuthStore } from '@/store/authStore';
import { Database, Users } from 'lucide-react';

export default function TelegramPage() {
  const { usuario } = useAuthStore();
  const canWrite = usuario?.rol === 'admin';
  const [tenantId, setTenantId] = useState('default');

  return (
    <PageShell>
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">Telegram</h1>
        <p className="text-sm text-gov-gray-500 dark:text-dark-muted mt-1">
          Canal opcional — la consola web es el flujo principal (DB-first)
        </p>
      </header>

      <section className="rounded-2xl border border-amber-200 bg-amber-50/80 p-4 text-sm text-amber-950 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-100">
        <p className="font-bold">Integración avanzada, no requerida para empezar</p>
        <p className="mt-1 text-xs text-amber-900/90 dark:text-amber-100/90">
          Usa Playground y <Link href="/admin/access" className="underline font-semibold">Usuarios consola</Link>{' '}
          para operar sin bot. Esta sección solo aplica si expones DuckClaw por Telegram.
        </p>
      </section>

      <SettingsSection
        titulo="Configuración Telegram"
        descripcion="DB-first para rutas webhook; .env queda como fallback de arranque."
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
    </PageShell>
  );
}
