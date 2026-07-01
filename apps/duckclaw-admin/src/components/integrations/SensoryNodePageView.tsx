'use client';

import Link from 'next/link';
import SettingsSection from '@/components/settings/SettingsSection';
import { ViewChrome, type EmbeddedViewProps } from '@/components/admin/embeddedView';
import { Mic } from 'lucide-react';
import { VoiceLabPanel } from '@/components/sensory/VoiceLabPanel';

const PM2_CMD = 'pm2 start config/ecosystem.sensory.config.cjs';
const HEALTH_CURL = 'curl http://100.99.72.63:8001/health';
const GATEWAY_HEALTH = 'curl -H "X-Admin-Key: $DUCKCLAW_ADMIN_API_KEY" http://127.0.0.1:8000/api/v1/sensory/health';

export default function SensoryNodePageView({ embedded = false }: EmbeddedViewProps) {
  return (
    <ViewChrome embedded={embedded}>
      {!embedded && (
        <header>
          <h1 className="text-3xl font-black dark:text-dark-text">Sensory node</h1>
          <p className="text-sm text-gov-gray-500 mt-1">
            STT (mlx-whisper) + TTS (OmniVoice) en Mac mini — paquete{' '}
            <code className="text-xs">integrations/sensory-node/</code>
          </p>
        </header>
      )}

      <SettingsSection
        titulo="Laboratorio de voz"
        descripcion="Nota de voz → transcripción → agente → respuesta hablada (sin Telegram)"
        icono={<Mic size={22} />}
      >
        <VoiceLabPanel />
      </SettingsSection>

      <SettingsSection
        titulo="API REST (fase interfaz)"
        descripcion="El gateway VPS expone proxy hacia el nodo edge en Tailscale"
        icono={<Mic size={22} />}
      >
        <ul className="text-sm text-gov-gray-600 dark:text-dark-muted space-y-2 list-disc pl-5">
          <li>
            <code className="text-xs">GET /api/v1/sensory/health</code>
          </li>
          <li>
            <code className="text-xs">POST /api/v1/sensory/transcribe</code> — audio base64 → texto
          </li>
          <li>
            <code className="text-xs">POST /api/v1/sensory/synthesize</code> — texto + voice_id → audio OGG
          </li>
        </ul>
        <p className="text-xs text-gov-gray-500 mt-3">
          Contrato completo: <code className="text-[10px]">integrations/sensory-node/SPEC.MD</code>
        </p>
      </SettingsSection>

      <SettingsSection
        titulo="Mac mini (PM2)"
        descripcion="Bind solo a IP Tailscale — no localhost ni en0"
        icono={<Mic size={22} />}
      >
        <pre className="text-xs font-mono bg-gov-gray-50 dark:bg-dark-bg p-4 rounded-xl overflow-x-auto whitespace-pre-wrap">
          {`# .env Mac mini
DUCKCLAW_SENSORY_BIND_HOST=100.99.72.63
DUCKCLAW_SENSORY_PORT=8001
DUCKCLAW_MCP_PORT=8010

uv sync --project integrations/sensory-node
${PM2_CMD}`}
        </pre>
        <p className="text-xs text-gov-gray-500 mt-3">
          Health directo: <code className="text-[10px]">{HEALTH_CURL}</code>
        </p>
      </SettingsSection>

      <SettingsSection
        titulo="Gateway VPS"
        descripcion="Variable DUCKCLAW_SENSORY_BASE_URL apunta al Mac por tailnet"
        icono={<Mic size={22} />}
      >
        <pre className="text-xs font-mono bg-gov-gray-50 dark:bg-dark-bg p-4 rounded-xl overflow-x-auto whitespace-pre-wrap">
          {`DUCKCLAW_SENSORY_BASE_URL=http://100.99.72.63:8001
# Proxy desde gateway local:
${GATEWAY_HEALTH}`}
        </pre>
        <p className="text-sm mt-3 text-gov-gray-600 dark:text-dark-muted">
          Telegram (voz entrante / TTS saliente) se integrará en una fase posterior; la interfaz HTTP ya está
          disponible para pruebas y clientes.
        </p>
        <p className="text-sm mt-3">
          <Link href="/integrations/edge-devices" className="text-gov-blue-700 dark:text-dark-cyan font-medium">
            Edge devices
          </Link>
          {' · '}
          <Link href="/integrations" className="text-gov-blue-700 dark:text-dark-cyan font-medium">
            Integraciones
          </Link>
        </p>
      </SettingsSection>
    </ViewChrome>
  );
}
