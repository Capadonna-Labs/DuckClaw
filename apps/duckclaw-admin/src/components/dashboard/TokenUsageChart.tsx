'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { adminService } from '@/services/adminService';
import type { OverviewUsage, UsageGroupBy } from '@/types/admin';

const INPUT_COLOR = '#60a5fa';
const OUTPUT_COLOR = '#34d399';
const USD_COLOR = '#f59e0b';

type Props = {
  initial?: OverviewUsage | null;
};

function formatUsd(value: number): string {
  if (value >= 1) return `$${value.toFixed(2)}`;
  if (value >= 0.01) return `$${value.toFixed(3)}`;
  return `$${value.toFixed(4)}`;
}

function formatTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(value);
}

export default function TokenUsageChart({ initial }: Props) {
  const [usage, setUsage] = useState<OverviewUsage | null>(initial ?? null);
  const [loading, setLoading] = useState(!initial);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(7);
  const [groupBy, setGroupBy] = useState<UsageGroupBy>('worker');
  const [workerId, setWorkerId] = useState('');
  const [sessionId, setSessionId] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await adminService.getOverviewMetrics({
        usage_days: days,
        usage_group_by: groupBy,
        worker_id: workerId || undefined,
        session_id: sessionId || undefined,
      });
      setUsage(data.usage ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo cargar el uso LLM');
    } finally {
      setLoading(false);
    }
  }, [days, groupBy, workerId, sessionId]);

  useEffect(() => {
    void load();
  }, [load]);

  const series = usage?.series ?? [];
  const summary = usage?.summary;
  const chartData = series.map((row) => ({
    label: row.label,
    Entrada: row.input_tokens,
    Salida: row.output_tokens,
    USD: row.cost_usd,
  }));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3 items-end">
        <FilterSelect
          label="Periodo"
          value={String(days)}
          onChange={(v) => setDays(Number(v))}
          options={[
            { value: '7', label: '7 días' },
            { value: '30', label: '30 días' },
          ]}
        />
        <FilterSelect
          label="Agrupar por"
          value={groupBy}
          onChange={(v) => setGroupBy(v as UsageGroupBy)}
          options={[
            { value: 'worker', label: 'Agente' },
            { value: 'day', label: 'Día' },
            { value: 'session', label: 'Conversación' },
          ]}
        />
        <FilterSelect
          label="Agente"
          value={workerId}
          onChange={setWorkerId}
          options={[
            { value: '', label: 'Todos' },
            ...(usage?.workers ?? []).map((w) => ({ value: w, label: w })),
          ]}
        />
        {groupBy !== 'session' && (
          <FilterSelect
            label="Conversación"
            value={sessionId}
            onChange={setSessionId}
            options={[
              { value: '', label: 'Todas' },
              ...(usage?.sessions ?? []).map((s) => ({
                value: s.session_id,
                label: `${s.session_id.slice(0, 12)}… (${formatTokens(s.total_tokens)})`,
              })),
            ]}
          />
        )}
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <SummaryCard label="Tokens totales" value={formatTokens(summary.total_tokens)} />
          <SummaryCard label="Entrada" value={formatTokens(summary.input_tokens)} />
          <SummaryCard label="Salida" value={formatTokens(summary.output_tokens)} />
          <SummaryCard label="Costo estimado" value={formatUsd(summary.cost_usd)} />
        </div>
      )}

      {error && (
        <p className="text-sm text-amber-700 dark:text-amber-300">{error}</p>
      )}

      {loading ? (
        <p className="text-sm text-gov-gray-500 dark:text-dark-muted py-8 text-center">
          Cargando uso LLM…
        </p>
      ) : !chartData.length ? (
        <p className="text-sm text-gov-gray-500 dark:text-dark-muted py-8 text-center">
          Sin datos de tokens en el periodo. Los nuevos chats registrarán uso automáticamente.
        </p>
      ) : (
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gov-gray-200 dark:stroke-slate-700" />
              <XAxis
                dataKey="label"
                tick={{ fill: 'currentColor', fontSize: 10 }}
                interval={0}
                angle={groupBy === 'session' ? -25 : 0}
                textAnchor={groupBy === 'session' ? 'end' : 'middle'}
                height={groupBy === 'session' ? 56 : 30}
                className="text-gov-gray-500 dark:text-dark-muted"
              />
              <YAxis
                yAxisId="tokens"
                tickFormatter={formatTokens}
                tick={{ fill: 'currentColor', fontSize: 11 }}
                className="text-gov-gray-500 dark:text-dark-muted"
              />
              <YAxis
                yAxisId="usd"
                orientation="right"
                tickFormatter={(v) => formatUsd(Number(v))}
                tick={{ fill: 'currentColor', fontSize: 11 }}
                className="text-gov-gray-500 dark:text-dark-muted"
              />
              <Tooltip
                formatter={(value: number, name: string) =>
                  name === 'USD' ? formatUsd(value) : formatTokens(value)
                }
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: '8px',
                  color: '#f1f5f9',
                }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar yAxisId="tokens" dataKey="Entrada" stackId="tokens" fill={INPUT_COLOR} />
              <Bar yAxisId="tokens" dataKey="Salida" stackId="tokens" fill={OUTPUT_COLOR} radius={[4, 4, 0, 0]} />
              <Line
                yAxisId="usd"
                type="monotone"
                dataKey="USD"
                stroke={USD_COLOR}
                strokeWidth={2}
                dot={{ r: 3 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="flex flex-col gap-1 text-xs">
      <span className="text-gov-gray-500 dark:text-dark-muted uppercase font-bold tracking-wider">
        {label}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-gov-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface px-2 py-1.5 text-sm min-w-[8rem]"
      >
        {options.map((opt) => (
          <option key={opt.value || '__all'} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-gov-gray-100 dark:border-dark-border px-3 py-2">
      <p className="text-[10px] uppercase font-bold tracking-wider text-gov-gray-500 dark:text-dark-muted">
        {label}
      </p>
      <p className="font-black text-lg text-gov-gray-900 dark:text-dark-text mt-0.5">{value}</p>
    </div>
  );
}
