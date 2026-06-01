'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { adminService } from '@/services/adminService';
import SettingsSection from '@/components/settings/SettingsSection';
import { PageShell } from '@/components/admin/PageShell';
import { TelegramWebhookRoutesEditor } from '@/components/telegram/TelegramWebhookRoutesEditor';
import { useAuthStore } from '@/store/authStore';
import { MessageSquare, Users } from 'lucide-react';

export default function TelegramPage() {
  const { usuario } = useAuthStore();
  const canWrite = usuario?.rol === 'admin';

  const [env, setEnv] = useState<Record<string, string>>({});
  const [tokenKey, setTokenKey] = useState('TELEGRAM_BOT_TOKEN');
  const [tokenVal, setTokenVal] = useState('');
  const [envMsg, setEnvMsg] = useState<string | null>(null);

  useEffect(() => {
    adminService.getEnv().then((e) => setEnv(e.values));
  }, []);

  const saveToken = async () => {
    await adminService.patchEnv({ [tokenKey]: tokenVal });
    setEnvMsg('Token actualizado (enmascarado en lectura)');
    setTokenVal('');
    adminService.getEnv().then((e) => setEnv(e.values));
  };

  return (
    <PageShell>
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">Telegram</h1>
        <p className="text-sm text-gov-gray-500 dark:text-dark-muted mt-1">
          Webhooks y tokens del bot
        </p>
      </header>

      <SettingsSection
        titulo="Token bot"
        descripcion="Configura el token del bot de Telegram"
        icono={<MessageSquare size={22} />}
      >
        <div className="space-y-3 max-w-lg">
          <select
            value={tokenKey}
            onChange={(e) => setTokenKey(e.target.value)}
            className="w-full px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-bg text-sm"
          >
            {Object.keys(env)
              .filter((k) => k.startsWith('TELEGRAM'))
              .map((k) => (
                <option key={k} value={k}>
                  {k} ({env[k]})
                </option>
              ))}
            <option value="TELEGRAM_BOT_TOKEN">TELEGRAM_BOT_TOKEN (nuevo)</option>
          </select>
          <input
            type="password"
            value={tokenVal}
            onChange={(e) => setTokenVal(e.target.value)}
            placeholder="Nuevo token (no se muestra el actual)"
            className="w-full px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-bg"
            disabled={!canWrite}
          />
          {canWrite && (
            <button
              type="button"
              onClick={saveToken}
              className="px-4 py-2 bg-gov-blue-700 text-white rounded-xl text-sm font-bold"
            >
              Guardar token
            </button>
          )}
          {envMsg && <p className="text-green-700 text-sm">{envMsg}</p>}
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
