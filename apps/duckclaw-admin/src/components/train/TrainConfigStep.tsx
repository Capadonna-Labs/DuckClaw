'use client';

import { useState } from 'react';
import { ChevronDown, Cpu, Cloud, Terminal } from 'lucide-react';

type TrainBackend = 'mlx' | 'huggingface' | 'ssh';
type PresetId = 'rapido' | 'balanceado' | 'alta';

interface LoraConfig {
  model: string;
  rank: number;
  alpha: number;
  lr: string;
  epochs: number;
  batchSize: number;
  maxSeqLen: number;
}

const PRESETS: { id: PresetId; label: string; desc: string; config: Partial<LoraConfig> }[] = [
  { id: 'rapido', label: 'Rapido', desc: '1 epoch · rank 4 · lr 2e-4', config: { epochs: 1, rank: 4, alpha: 8, lr: '2e-4', batchSize: 4, maxSeqLen: 512 } },
  { id: 'balanceado', label: 'Balanceado', desc: '2 epochs · rank 8 · lr 1e-4', config: { epochs: 2, rank: 8, alpha: 16, lr: '1e-4', batchSize: 4, maxSeqLen: 1024 } },
  { id: 'alta', label: 'Alta calidad', desc: '3 epochs · rank 16 · lr 5e-5', config: { epochs: 3, rank: 16, alpha: 32, lr: '5e-5', batchSize: 2, maxSeqLen: 2048 } },
];

const MODEL_SUGGESTIONS = [
  'Qwen/Qwen3-0.6B',
  'google/gemma-4-1b',
  'meta-llama/Llama-3.2-1B',
  'HuggingFaceTB/SmolLM2-135M',
];

const BACKENDS: { id: TrainBackend; label: string; icon: typeof Cpu }[] = [
  { id: 'mlx', label: 'Mac mini (MLX)', icon: Cpu },
  { id: 'huggingface', label: 'HuggingFace AutoTrain', icon: Cloud },
  { id: 'ssh', label: 'Custom SSH', icon: Terminal },
];

interface TrainConfigStepProps {
  config: LoraConfig;
  onConfigChange: (c: LoraConfig) => void;
  backend: TrainBackend;
  onBackendChange: (b: TrainBackend) => void;
}

export default function TrainConfigStep({ config, onConfigChange, backend, onBackendChange }: TrainConfigStepProps) {
  const [activePreset, setActivePreset] = useState<PresetId | null>('balanceado');
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const applyPreset = (p: PresetId) => {
    setActivePreset(p);
    const preset = PRESETS.find((x) => x.id === p)!;
    onConfigChange({ ...config, ...preset.config });
  };

  const updateField = <K extends keyof LoraConfig>(key: K, value: LoraConfig[K]) => {
    setActivePreset(null);
    onConfigChange({ ...config, [key]: value });
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-black dark:text-dark-text">Modelo base</h2>
        <p className="text-xs text-gov-gray-500 mt-0.5">Modelo HuggingFace sobre el cual aplicar LoRA.</p>
      </div>

      <div className="space-y-2">
        <input
          type="text"
          value={config.model}
          onChange={(e) => updateField('model', e.target.value)}
          placeholder="org/model-name"
          className="w-full rounded-xl border border-gov-gray-200 bg-white px-3 py-2.5 text-sm font-mono dark:border-dark-border dark:bg-dark-bg dark:text-dark-text placeholder:text-gov-gray-400"
        />
        <div className="flex flex-wrap gap-1.5">
          {MODEL_SUGGESTIONS.map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => onConfigChange({ ...config, model: m })}
              className={`rounded-lg border px-2 py-1 text-[11px] font-bold transition-colors ${
                config.model === m
                  ? 'border-gov-blue-700 bg-gov-blue-50 text-gov-blue-800 dark:bg-gov-blue-950/30 dark:text-gov-blue-400 dark:border-gov-blue-500'
                  : 'border-gov-gray-200 text-gov-gray-500 hover:border-gov-blue-300 dark:border-dark-border dark:hover:border-gov-blue-700'
              }`}
            >
              {m.split('/')[1]}
            </button>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-lg font-black dark:text-dark-text">Preset</h2>
        <p className="text-xs text-gov-gray-500 mt-0.5">Configuracion predefinida de hiperparametros.</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {PRESETS.map(({ id, label, desc }) => (
          <button
            key={id}
            type="button"
            onClick={() => applyPreset(id)}
            className={`text-left rounded-2xl border p-4 transition-colors ${
              activePreset === id
                ? 'border-gov-blue-700 bg-gov-blue-50 dark:bg-gov-blue-950/30 dark:border-gov-blue-500'
                : 'border-gov-gray-200 hover:border-gov-blue-300 dark:border-dark-border dark:hover:border-gov-blue-700'
            }`}
          >
            <p className="font-bold text-sm dark:text-dark-text">{label}</p>
            <p className="text-[11px] text-gov-gray-500 mt-0.5 font-mono">{desc}</p>
          </button>
        ))}
      </div>

      <div className="rounded-2xl border dark:border-dark-border overflow-hidden">
        <button
          type="button"
          onClick={() => setAdvancedOpen((o) => !o)}
          className="w-full flex items-center justify-between px-4 py-3 text-sm font-bold dark:text-dark-text hover:bg-gov-gray-50 dark:hover:bg-dark-bg transition-colors"
        >
          Avanzado
          <ChevronDown size={16} className={`transition-transform ${advancedOpen ? 'rotate-180' : ''}`} />
        </button>
        {advancedOpen && (
          <div className="border-t dark:border-dark-border px-4 py-4 grid gap-4 sm:grid-cols-3">
            {([
              { key: 'rank' as const, label: 'LoRA Rank', type: 'number' },
              { key: 'alpha' as const, label: 'LoRA Alpha', type: 'number' },
              { key: 'lr' as const, label: 'Learning Rate', type: 'text' },
              { key: 'epochs' as const, label: 'Epochs', type: 'number' },
              { key: 'batchSize' as const, label: 'Batch Size', type: 'number' },
              { key: 'maxSeqLen' as const, label: 'Max Seq Length', type: 'number' },
            ] as const).map(({ key, label, type }) => (
              <div key={key}>
                <label className="block text-[11px] font-bold text-gov-gray-500 mb-1">{label}</label>
                <input
                  type={type}
                  value={config[key]}
                  onChange={(e) =>
                    updateField(key, type === 'number' ? Number(e.target.value) : e.target.value as any)
                  }
                  className="w-full rounded-lg border border-gov-gray-200 bg-white px-2.5 py-1.5 text-sm font-mono dark:border-dark-border dark:bg-dark-bg dark:text-dark-text"
                />
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <h2 className="text-lg font-black dark:text-dark-text">Backend de entrenamiento</h2>
        <p className="text-xs text-gov-gray-500 mt-0.5">Donde se ejecutara el fine-tuning.</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {BACKENDS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => onBackendChange(id)}
            className={`flex items-center gap-3 rounded-2xl border p-4 transition-colors ${
              backend === id
                ? 'border-gov-blue-700 bg-gov-blue-50 dark:bg-gov-blue-950/30 dark:border-gov-blue-500'
                : 'border-gov-gray-200 hover:border-gov-blue-300 dark:border-dark-border dark:hover:border-gov-blue-700'
            }`}
          >
            <Icon size={18} className={backend === id ? 'text-gov-blue-700 dark:text-gov-blue-400' : 'text-gov-gray-400'} />
            <span className="font-bold text-sm dark:text-dark-text">{label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export type { LoraConfig, TrainBackend };
