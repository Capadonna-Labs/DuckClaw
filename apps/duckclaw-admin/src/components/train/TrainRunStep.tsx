'use client';

import { Activity, Play, Radio } from 'lucide-react';
import type { LoraConfig, TrainBackend } from './TrainConfigStep';

interface TrainRunStepProps {
  config: LoraConfig;
  backend: TrainBackend;
}

const BACKEND_LABELS: Record<TrainBackend, string> = {
  mlx: 'Mac mini (MLX via Tailscale)',
  huggingface: 'HuggingFace AutoTrain',
  ssh: 'Custom SSH',
};

export default function TrainRunStep({ config, backend }: TrainRunStepProps) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-black dark:text-dark-text">Entrenamiento</h2>
        <p className="text-xs text-gov-gray-500 mt-0.5">Ejecuta LoRA fine-tuning y monitorea el progreso.</p>
      </div>

      <div className="rounded-2xl border dark:border-dark-border p-4 space-y-3">
        <div className="flex items-center gap-2">
          <Radio size={14} className="text-gov-gray-400" />
          <span className="text-xs font-bold text-gov-gray-400 uppercase tracking-wide">Resumen de configuracion</span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'Modelo', value: config.model.split('/').pop() || '—' },
            { label: 'Backend', value: BACKEND_LABELS[backend] },
            { label: 'Epochs', value: String(config.epochs) },
            { label: 'LoRA Rank', value: String(config.rank) },
          ].map(({ label, value }) => (
            <div key={label}>
              <p className="text-[10px] font-bold uppercase tracking-wide text-gov-gray-400">{label}</p>
              <p className="text-sm font-bold dark:text-dark-text truncate mt-0.5">{value}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled
          className="inline-flex items-center gap-2 rounded-xl bg-gov-blue-700 px-5 py-2.5 text-sm font-black text-white opacity-60 cursor-not-allowed"
        >
          <Play size={16} />
          Iniciar entrenamiento
        </button>
        <span className="text-xs text-gov-gray-400 italic">Proximamente</span>
      </div>

      <div>
        <div className="flex items-center gap-2 mb-2">
          <Activity size={14} className="text-gov-gray-400" />
          <span className="text-xs font-bold text-gov-gray-400 uppercase tracking-wide">Training loss</span>
        </div>
        <div className="rounded-2xl border border-dashed border-gov-gray-200 dark:border-dark-border h-48 flex items-center justify-center">
          <div className="text-center">
            <Activity size={32} className="mx-auto text-gov-gray-200 dark:text-gov-gray-700" />
            <p className="text-xs text-gov-gray-400 mt-2">La grafica de loss aparecera aqui durante el entrenamiento.</p>
          </div>
        </div>
      </div>

      <div>
        <p className="text-xs font-bold text-gov-gray-400 uppercase tracking-wide mb-2">Logs</p>
        <div className="rounded-2xl bg-gov-gray-900 dark:bg-black/60 border border-gov-gray-800 dark:border-dark-border p-4 h-40 overflow-y-auto font-mono text-xs text-gov-gray-500">
          <p className="text-gov-gray-600">$ Pendiente de conexion con nodo de entrenamiento...</p>
          <p className="text-gov-gray-700 mt-1">Configura el backend y presiona &quot;Iniciar entrenamiento&quot; para comenzar.</p>
        </div>
      </div>
    </div>
  );
}
