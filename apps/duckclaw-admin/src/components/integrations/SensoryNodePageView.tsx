'use client';

import Link from 'next/link';
import { ViewChrome, type EmbeddedViewProps } from '@/components/admin/embeddedView';
import { VoiceLabPanel } from '@/components/sensory/VoiceLabPanel';

const PM2_CMD = 'pm2 start config/ecosystem.sensory.config.cjs';
const HEALTH_CURL =
  'curl http://${DUCKCLAW_SENSORY_BIND_HOST:-192.0.2.20}:${DUCKCLAW_SENSORY_PORT:-8001}/health';
const GATEWAY_HEALTH =
  'curl -H "X-Admin-Key: $DUCKCLAW_ADMIN_API_KEY" http://127.0.0.1:8000/api/v1/sensory/health';

export default function SensoryNodePageView({ embedded = false }: EmbeddedViewProps) {
  return (
    <ViewChrome embedded={embedded}>
      <div className="space-y-4">
        {!embedded && (
          <header className="border-b border-gov-gray-200 pb-4 dark:border-dark-border">
            <h1 className="text-2xl font-bold text-gov-gray-900 dark:text-dark-text">Sensory node</h1>
            <p className="mt-1 text-sm text-gov-gray-600 dark:text-dark-muted">
              STT + TTS en Mac mini — integrations/sensory-node/
            </p>
          </header>
        )}

        <div className="grid gap-4 lg:grid-cols-12">
          <section className="rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface lg:col-span-8">
            <div className="border-b border-gov-gray-100 px-4 py-3 dark:border-dark-border">
              <h2 className="text-base font-semibold text-gov-gray-900 dark:text-dark-text">
                Laboratorio de voz
              </h2>
              <p className="mt-0.5 text-xs text-gov-gray-500 dark:text-dark-muted">
                Nota de voz → transcripción → agente → respuesta hablada
              </p>
            </div>
            <div className="p-4">
              <VoiceLabPanel />
            </div>
          </section>

          <aside className="space-y-4 lg:col-span-4">
            <section className="rounded-xl border border-gov-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
              <p className="text-sm font-semibold text-gov-gray-900 dark:text-dark-text">API REST</p>
              <ul className="mt-2 space-y-1.5 text-xs text-gov-gray-600 dark:text-dark-muted">
                <li>
                  <code className="font-mono">GET /api/v1/sensory/health</code>
                </li>
                <li>
                  <code className="font-mono">POST /api/v1/sensory/transcribe</code>
                </li>
                <li>
                  <code className="font-mono">POST /api/v1/sensory/synthesize</code>
                </li>
              </ul>
              <p className="mt-2 text-xs text-gov-gray-500">
                Código: integrations/sensory-node/
              </p>
            </section>

            <section className="rounded-xl border border-gov-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
              <p className="text-sm font-semibold text-gov-gray-900 dark:text-dark-text">Mac mini (PM2)</p>
              <pre className="scrollbar-hide mt-2 overflow-x-auto whitespace-pre-wrap rounded-lg bg-gov-gray-50 p-3 font-mono text-[11px] dark:bg-dark-bg">
                {`DUCKCLAW_SENSORY_BIND_HOST=192.0.2.20
DUCKCLAW_SENSORY_PORT=8001
uv sync --project integrations/sensory-node
${PM2_CMD}`}
              </pre>
              <p className="mt-2 break-all font-mono text-[10px] text-gov-gray-500">{HEALTH_CURL}</p>
            </section>

            <section className="rounded-xl border border-gov-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
              <p className="text-sm font-semibold text-gov-gray-900 dark:text-dark-text">Gateway host</p>
              <pre className="scrollbar-hide mt-2 overflow-x-auto whitespace-pre-wrap rounded-lg bg-gov-gray-50 p-3 font-mono text-[11px] dark:bg-dark-bg">
                {`DUCKCLAW_SENSORY_BASE_URL=http://192.0.2.20:8001
${GATEWAY_HEALTH}`}
              </pre>
              <p className="mt-3 text-xs">
                <Link
                  href="/integraciones?tab=dispositivos"
                  className="font-medium text-gov-blue-700 dark:text-dark-cyan"
                >
                  Dispositivos
                </Link>
              </p>
            </section>
          </aside>
        </div>
      </div>
    </ViewChrome>
  );
}
