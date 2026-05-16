'use client';

import { useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';
import SettingsSection from '@/components/settings/SettingsSection';
import { MessageSquare } from 'lucide-react';

export default function TelegramPage() {
  const [routes, setRoutes] = useState<{ bot: string; path: string }[]>([]);
  const [env, setEnv] = useState<Record<string, string>>({});
  const [tokenKey, setTokenKey] = useState('TELEGRAM_BOT_TOKEN');
  const [tokenVal, setTokenVal] = useState('');
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    adminService.getTelegramRoutes().then((r) => setRoutes(r.routes));
    adminService.getEnv().then((e) => setEnv(e.values));
  }, []);

  const saveToken = async () => {
    await adminService.patchEnv({ [tokenKey]: tokenVal });
    setMsg('Token actualizado (enmascarado en lectura)');
    setTokenVal('');
    adminService.getEnv().then((e) => setEnv(e.values));
  };

  return (
    <motionPage>
      <h1 className="text-3xl font-black dark:text-dark-text">Telegram</h1>
      <SettingsSection
        titulo="Rutas webhook"
        descripcion="DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES"
        icono={<MessageSquare size={22} />}
      >
        <ul className="space-y-2 text-sm font-mono">
          {routes.length === 0 && <li className="text-gov-gray-500">Sin rutas configuradas</li>}
          {routes.map((r) => (
            <li key={r.bot} className="p-2 bg-gov-gray-50 dark:bg-dark-bg rounded-lg">
              {r.bot} → {r.path}
            </li>
          ))}
        </ul>
      </SettingsSection>
      <SettingsSection titulo="Token bot" descripcion="Progressive disclosure — valor nuevo" icono={<MessageSquare size={22} />}>
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
          />
          <button
            type="button"
            onClick={saveToken}
            className="px-4 py-2 bg-gov-blue-700 text-white rounded-xl text-sm font-bold"
          >
            Guardar
          </button>
          {msg && <p className="text-green-700 text-sm">{msg}</p>}
        </div>
      </SettingsSection>
    </motionPage>
  );
}

function motionPage({ children }: { children: React.ReactNode }) {
  return <div className="space-y-8">{children}</div>;
}
