'use client';

import Link from 'next/link';
import { PageShell } from '@/components/admin/PageShell';
import SettingsSection from '@/components/settings/SettingsSection';
import { Cpu, ExternalLink } from 'lucide-react';

const STREAMLIT_CMD =
  'uv run --project integrations/edge-devices streamlit run integrations/edge-devices/src/duckclaw_edge_devices/app.py';

const BUILD_NATIVE_CMD = `cd integrations/edge-devices/native
g++ -O3 -shared -fPIC -std=c++14 edge_core.cpp -o libedgecore.so`;

export default function EdgeDevicesPage() {
  return (
    <PageShell>
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">Edge devices</h1>
        <p className="text-sm text-gov-gray-500 mt-1">
          Telemetría <code className="text-xs">libedgecore</code> — paquete{' '}
          <code className="text-xs">integrations/edge-devices/</code>
        </p>
      </header>

      <SettingsSection
        titulo="Dashboard Streamlit"
        descripcion="La UI de telemetría corre fuera del admin Next.js (proceso local)"
        icono={<Cpu size={22} />}
      >
        <p className="text-sm text-gov-gray-600 dark:text-dark-muted mb-3">
          Desde la raíz del monorepo:
        </p>
        <pre className="text-xs font-mono bg-gov-gray-50 dark:bg-dark-bg p-4 rounded-xl overflow-x-auto">
          {STREAMLIT_CMD}
        </pre>
        <p className="text-xs text-gov-gray-500 mt-3">
          Por defecto Streamlit escucha en{' '}
          <a
            href="http://127.0.0.1:8501"
            target="_blank"
            rel="noopener noreferrer"
            className="text-gov-blue-700 dark:text-dark-cyan inline-flex items-center gap-1"
          >
            http://127.0.0.1:8501
            <ExternalLink size={12} />
          </a>
          . Documentación:{' '}
          <code className="text-[10px]">integrations/edge-devices/EDGE_DEVICES_STREAMLIT.md</code>
        </p>
      </SettingsSection>

      <SettingsSection
        titulo="Compilar librería nativa"
        descripcion="libedgecore.so no va en git; compilar tras pull en Linux/VPS"
        icono={<Cpu size={22} />}
      >
        <pre className="text-xs font-mono bg-gov-gray-50 dark:bg-dark-bg p-4 rounded-xl overflow-x-auto whitespace-pre-wrap">
          {BUILD_NATIVE_CMD}
        </pre>
        <p className="text-xs text-gov-gray-500 mt-3">
          Opcional: <code className="text-[10px]">export DUCKCLAW_EDGE_LIB_PATH=/ruta/libedgecore.so</code>
        </p>
      </SettingsSection>

      <SettingsSection titulo="Bridge Redis" descripcion="Workers vía duckclaw.forge.skills" icono={<Cpu size={22} />}>
        <p className="text-sm text-gov-gray-600 dark:text-dark-muted">
          El script <code className="text-xs">edge_bridge</code> usa el mismo cliente Python. Requiere{' '}
          <code className="text-xs">integrations/edge-devices</code> instalado en editable y Redis +
          DuckClaw-DB-Writer activos.
        </p>
        <p className="text-sm mt-3">
          <Link href="/telegram" className="text-gov-blue-700 dark:text-dark-cyan font-medium">
            ← Telegram
          </Link>
          {' · '}
          <Link href="/integrations" className="text-gov-blue-700 dark:text-dark-cyan font-medium">
            Integraciones
          </Link>
        </p>
      </SettingsSection>
    </PageShell>
  );
}
