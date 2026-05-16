'use client';

import { useState } from 'react';
import { adminService } from '@/services/adminService';
import SettingsSection from '@/components/settings/SettingsSection';
import { Activity } from 'lucide-react';

export default function TracesPage() {
  const [tenantId, setTenantId] = useState('default');
  const [sessionId, setSessionId] = useState('');
  const [messages, setMessages] = useState<unknown[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setError(null);
    try {
      const r = await adminService.getChatHistory(tenantId, sessionId);
      setMessages(r.messages ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    }
  };

  return (
    <div className="space-y-8">
      <h1 className="text-3xl font-black dark:text-dark-text">Traces</h1>
      <SettingsSection
        titulo="Historial Redis"
        descripcion="Activity Stream — actor / rol / contenido"
        icono={<Activity size={22} />}
      >
        <div className="flex flex-wrap gap-2 mb-4">
          <input
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
            className="px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-bg text-sm"
            placeholder="tenant_id"
          />
          <input
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
            className="flex-1 min-w-[200px] px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-bg text-sm font-mono"
            placeholder="session_id / chat_id"
          />
          <button
            type="button"
            onClick={load}
            className="px-4 py-2 bg-gov-blue-700 text-white rounded-xl text-sm font-bold"
          >
            Cargar
          </button>
        </div>
        {error && <p className="text-red-600 text-sm">{error}</p>}
        <ul className="space-y-2 max-h-[480px] overflow-y-auto text-sm">
          {messages.map((m, i) => (
            <li key={i} className="p-3 rounded-xl bg-gov-gray-50 dark:bg-dark-bg font-mono text-xs whitespace-pre-wrap">
              {JSON.stringify(m, null, 2)}
            </li>
          ))}
        </ul>
      </SettingsSection>
    </div>
  );
}
