'use client';

import Link from 'next/link';
import SettingsSection from '@/components/settings/SettingsSection';
import { PageShell } from '@/components/admin/PageShell';
import { TelegramWebhookRoutesEditor } from '@/components/telegram/TelegramWebhookRoutesEditor';
import { useAuthStore } from '@/store/authStore';
import { Database, Users } from 'lucide-react';

export default function TelegramPage() {
  const { usuario } = useAuthStore();
  const canWrite = usuario?.rol === 'admin';

  return (
    <PageShell>
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">Telegram</h1>
        <p className="text-sm text-gov-gray-500 dark:text-dark-muted mt-1">
          Webhooks y tokens del bot
        </p>
      </header>

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
        titulo="Usuarios autorizados"
        descripcion="Usuarios que pueden usar el bot"
        icono={<Users size={22} />}
      >
        <p className="text-sm text-gov-gray-600 dark:text-dark-muted">
          Gestiona usuarios y roles en{' '}
          <Link href="/admin/access" className="text-gov-blue-700 font-bold underline">
            Acceso → Telegram
          </Link>
          . La misma tabla que el comando <code className="font-mono text-xs">/team</code> en el bot.
        </p>
      </SettingsSection>

      <TelegramWebhookRoutesEditor canWrite={canWrite} />
    </PageShell>
  );
}
