'use client';

import { useEffect, useState } from 'react';
import { Database, FileUp, Globe, RefreshCw } from 'lucide-react';
import { adminService } from '@/services/adminService';

type DataSource = 'traces' | 'upload' | 'huggingface';

type TracePreviewRow = {
  instruction: string;
  response: string;
};

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

function avgLen(rows: TracePreviewRow[]): number | null {
  const pairs = rows.filter((r) => r.instruction || r.response);
  if (!pairs.length) return null;
  const total = pairs.reduce((acc, r) => acc + r.instruction.length + r.response.length, 0);
  return Math.round(total / pairs.length);
}

export default function TrainDataStep({ source, onSourceChange, hfDataset, onHfDatasetChange }: TrainDataStepProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tracePath, setTracePath] = useState<string | null>(null);
  const [traceRows, setTraceRows] = useState<TracePreviewRow[]>([]);
  const [totalLines, setTotalLines] = useState<number | null>(null);
  const [fileCount, setFileCount] = useState<number | null>(null);
  const [tracesDir, setTracesDir] = useState<string | null>(null);

  const loadTraces = async () => {
    if (source !== 'traces') return;
    setLoading(true);
    setError(null);
    try {
      const status = await adminService.getTrainStatus();
      const recent = status.conversation_traces?.recent ?? [];
      setFileCount(status.conversation_traces?.file_count ?? recent.length);
      setTracesDir(status.paths?.conversation_traces ?? null);
      if (!recent.length) {
        setTracePath(null);
        setTraceRows([]);
        setTotalLines(0);
        setError('No hay archivos traces.jsonl en el datalake del gateway.');
        return;
      }
      const latest = recent[0];
      setTracePath(latest.relative_path);
      const sample = await adminService.getTrainTraceSample(
        'conversation_traces',
        latest.relative_path,
        5
      );
      const rows = (sample.samples ?? []).map((s) => {
        const row = s as { instruction?: string; response?: string };
        return {
          instruction: (row.instruction || '').trim() || '—',
          response: (row.response || '').trim() || '—',
        };
      });
      setTraceRows(rows);
      setTotalLines(sample.total_lines_estimate ?? latest.line_count ?? rows.length);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'No se pudo cargar las trazas';
      setError(msg);
      setTraceRows([]);
      setTotalLines(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (source === 'traces') {
      void loadTraces();
    }
  }, [source]);

  const avg = source === 'traces' ? avgLen(traceRows) : null;

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

      {source === 'traces' && (
        <div className="flex items-center justify-between gap-3">
          <p className="text-[11px] text-gov-gray-500 truncate">
            {tracesDir ? `Lake: ${tracesDir}` : 'Conectando al gateway...'}
            {tracePath ? ` · ${tracePath}` : ''}
          </p>
          <button
            type="button"
            onClick={() => void loadTraces()}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-bold text-gov-blue-800 dark:text-dark-cyan disabled:opacity-50"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
            Actualizar
          </button>
        </div>
      )}

      <div className="rounded-2xl border border-dashed border-gov-gray-200 dark:border-dark-border p-6">
        <div className="text-center">
          <p className="text-sm font-bold text-gov-gray-400 dark:text-gov-gray-500">Vista previa del dataset</p>
          <p className="text-xs text-gov-gray-400 mt-1">
            {source === 'traces'
              ? loading
                ? 'Cargando conversation traces del gateway...'
                : error
                  ? error
                  : traceRows.length
                    ? `${totalLines ?? '—'} filas en el archivo mas reciente (${fileCount ?? 0} archivos en el lake).`
                    : 'Sin muestras en el archivo mas reciente.'
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
            <tbody className="text-gov-gray-600 dark:text-gov-gray-300">
              {(source === 'traces' && traceRows.length ? traceRows : [{ instruction: '—', response: '—' }])
                .slice(0, 5)
                .map((row, i) => (
                  <tr key={i} className="border-b border-dashed dark:border-dark-border align-top">
                    <td className="py-2 pr-4 tabular-nums">{i + 1}</td>
                    <td className="py-2 pr-4 max-w-xs whitespace-pre-wrap break-words">{row.instruction}</td>
                    <td className="py-2 max-w-xs whitespace-pre-wrap break-words">{row.response}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Filas', value: source === 'traces' ? (totalLines != null ? String(totalLines) : '—') : '—' },
          { label: 'Long. media', value: source === 'traces' && avg != null ? String(avg) : '—' },
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
