'use client';

import { Database, FileUp, Globe } from 'lucide-react';

type DataSource = 'traces' | 'upload' | 'huggingface';

const SOURCES: { id: DataSource; label: string; desc: string; icon: typeof Database }[] = [
  { id: 'traces', label: 'Conversation traces', desc: 'Historial de conversaciones DuckClaw', icon: Database },
  { id: 'upload', label: 'Upload JSONL', desc: 'Sube un archivo .jsonl con pares instruccion/respuesta', icon: FileUp },
  { id: 'huggingface', label: 'HuggingFace dataset', desc: 'Descarga un dataset publico del Hub', icon: Globe },
];

interface TrainDataStepProps {
  source: DataSource;
  onSourceChange: (s: DataSource) => void;
  hfDataset: string;
  onHfDatasetChange: (v: string) => void;
}

export default function TrainDataStep({ source, onSourceChange, hfDataset, onHfDatasetChange }: TrainDataStepProps) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-black dark:text-dark-text">Fuente de datos</h2>
        <p className="text-xs text-gov-gray-500 mt-0.5">Elige de donde vienen los datos de entrenamiento.</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {SOURCES.map(({ id, label, desc, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => onSourceChange(id)}
            className={`text-left rounded-2xl border p-4 transition-colors ${
              source === id
                ? 'border-gov-blue-700 bg-gov-blue-50 dark:bg-gov-blue-950/30 dark:border-gov-blue-500'
                : 'border-gov-gray-200 hover:border-gov-blue-300 dark:border-dark-border dark:hover:border-gov-blue-700'
            }`}
          >
            <Icon size={20} className={source === id ? 'text-gov-blue-700 dark:text-gov-blue-400' : 'text-gov-gray-400'} />
            <p className="font-bold text-sm mt-2 dark:text-dark-text">{label}</p>
            <p className="text-[11px] text-gov-gray-500 mt-0.5">{desc}</p>
          </button>
        ))}
      </div>

      {source === 'huggingface' && (
        <div className="space-y-2">
          <label className="block text-xs font-bold dark:text-dark-text">Dataset ID</label>
          <input
            type="text"
            value={hfDataset}
            onChange={(e) => onHfDatasetChange(e.target.value)}
            placeholder="tatsu-lab/alpaca"
            className="w-full rounded-xl border border-gov-gray-200 bg-white px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg dark:text-dark-text placeholder:text-gov-gray-400"
          />
        </div>
      )}

      <div className="rounded-2xl border border-dashed border-gov-gray-200 dark:border-dark-border p-6">
        <div className="text-center">
          <p className="text-sm font-bold text-gov-gray-400 dark:text-gov-gray-500">Vista previa del dataset</p>
          <p className="text-xs text-gov-gray-400 mt-1">
            {source === 'traces'
              ? 'Se cargaran las conversation traces del gateway al conectar.'
              : source === 'upload'
                ? 'Arrastra un .jsonl aqui o haz click para seleccionar.'
                : hfDataset
                  ? `Se descargara ${hfDataset} del Hub.`
                  : 'Ingresa un dataset ID arriba.'}
          </p>
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b dark:border-dark-border text-gov-gray-400">
                <th className="text-left py-2 pr-4 font-bold">#</th>
                <th className="text-left py-2 pr-4 font-bold">instruction</th>
                <th className="text-left py-2 font-bold">response</th>
              </tr>
            </thead>
            <tbody className="text-gov-gray-300 dark:text-gov-gray-600">
              {[1, 2, 3].map((i) => (
                <tr key={i} className="border-b border-dashed dark:border-dark-border">
                  <td className="py-2 pr-4 tabular-nums">{i}</td>
                  <td className="py-2 pr-4 italic">—</td>
                  <td className="py-2 italic">—</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Filas', value: '—' },
          { label: 'Long. media', value: '—' },
          { label: 'Formato', value: source === 'traces' ? 'chat' : '—' },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-xl border dark:border-dark-border px-3 py-2 text-center">
            <p className="text-[10px] font-bold uppercase tracking-wide text-gov-gray-400">{label}</p>
            <p className="text-sm font-black dark:text-dark-text mt-0.5">{value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export type { DataSource };
