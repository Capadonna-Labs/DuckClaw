'use client';

import { useState } from 'react';
import { Database, Settings2, Play } from 'lucide-react';
import TrainDataStep, { type DataSource } from '@/components/train/TrainDataStep';
import TrainConfigStep, { type LoraConfig, type TrainBackend } from '@/components/train/TrainConfigStep';
import TrainRunStep from '@/components/train/TrainRunStep';

type StepId = 'data' | 'config' | 'run';

const STEPS: { id: StepId; label: string; icon: typeof Database }[] = [
  { id: 'data', label: '1. Datos', icon: Database },
  { id: 'config', label: '2. Configuracion', icon: Settings2 },
  { id: 'run', label: '3. Entrenar', icon: Play },
];

const DEFAULT_CONFIG: LoraConfig = {
  model: 'Qwen/Qwen3-0.6B',
  rank: 8,
  alpha: 16,
  lr: '1e-4',
  epochs: 2,
  batchSize: 4,
  maxSeqLen: 1024,
};

export default function TrainPage() {
  const [step, setStep] = useState<StepId>('data');
  const [source, setSource] = useState<DataSource>('traces');
  const [hfDataset, setHfDataset] = useState('');
  const [config, setConfig] = useState<LoraConfig>(DEFAULT_CONFIG);
  const [backend, setBackend] = useState<TrainBackend>('mlx');

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">Train</h1>
        <p className="text-sm text-gov-gray-500 mt-1">
          Fine-tuning con LoRA — conecta tu dataset, configura hiperparametros y entrena.
        </p>
      </header>

      <nav className="flex gap-1 rounded-2xl border dark:border-dark-border bg-gov-gray-50 dark:bg-dark-bg p-1">
        {STEPS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setStep(id)}
            className={`flex-1 flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-bold transition-colors ${
              step === id
                ? 'bg-white text-gov-blue-800 shadow-sm dark:bg-dark-surface dark:text-dark-text'
                : 'text-gov-gray-400 hover:text-gov-gray-600 dark:hover:text-gov-gray-300'
            }`}
          >
            <Icon size={16} />
            {label}
          </button>
        ))}
      </nav>

      <div className="rounded-3xl border dark:border-dark-border bg-white dark:bg-dark-surface p-6 shadow-sm">
        {step === 'data' && (
          <TrainDataStep
            source={source}
            onSourceChange={setSource}
            hfDataset={hfDataset}
            onHfDatasetChange={setHfDataset}
          />
        )}
        {step === 'config' && (
          <TrainConfigStep
            config={config}
            onConfigChange={setConfig}
            backend={backend}
            onBackendChange={setBackend}
          />
        )}
        {step === 'run' && (
          <TrainRunStep config={config} backend={backend} />
        )}
      </div>
    </div>
  );
}
