import SettingsSection from '@/components/settings/SettingsSection';
import { GraduationCap, Terminal } from 'lucide-react';

export default function TrainPage() {
  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">Train</h1>
        <p className="text-sm text-gov-gray-500 mt-1">
          SFT / GRPO pipeline — CLI only (admin API removed)
        </p>
      </header>

      <SettingsSection
        titulo="Usar CLI"
        descripcion="El panel admin ya no ejecuta el pipeline de entrenamiento."
        icono={<GraduationCap size={22} />}
      >
        <p className="text-sm text-gov-gray-600 dark:text-gov-gray-400 mb-4">
          Ejecuta el pipeline desde el monorepo con DuckOps o los scripts bajo{' '}
          <code className="font-mono text-xs">packages/agents/train/</code>.
        </p>
        <pre className="p-4 rounded-xl bg-gov-gray-50 dark:bg-dark-bg text-xs font-mono whitespace-pre-wrap">
          {`# Desde la raíz del repo
uv run duckops train -c packages/agents/train/config/lora_config.yaml

# Trazas y datasets
packages/agents/train/conversation_traces/
packages/agents/train/gemma4/`}
        </pre>
      </SettingsSection>

      <SettingsSection
        titulo="GRPO (alternativa)"
        descripcion="Captura con reward_metadata vía variable de entorno del gateway"
        icono={<Terminal size={22} />}
        defaultOpen={false}
      >
        <pre className="p-3 rounded-xl bg-gov-gray-50 dark:bg-dark-bg text-xs font-mono">
          DUCKCLAW_CONVERSATION_TRACES_FORMAT=grpo
        </pre>
        <p className="mt-3 text-xs text-gov-gray-500">
          Spec: specs/features/platform/SFT_DATASET_FORMAT.md
        </p>
      </SettingsSection>
    </div>
  );
}
