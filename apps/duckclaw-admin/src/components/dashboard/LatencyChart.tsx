'use client';

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { OverviewLatencyRow } from '@/types/admin';

const STROKE_COLOR = '#60a5fa';

type Props = {
  data: OverviewLatencyRow[];
};

export default function LatencyChart({ data }: Props) {
  if (!data.length) {
    return (
      <p className="text-sm text-gov-gray-500 dark:text-dark-muted py-8 text-center">
        Sin datos en el periodo
      </p>
    );
  }

  const chartData = data.map((row) => ({
    hour: row.hour,
    latency: row.avg_latency,
  }));

  return (
    <div className="h-64 w-full rounded-xl bg-slate-50 dark:bg-[#1e293b] p-2">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="latencyFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={STROKE_COLOR} stopOpacity={0.35} />
              <stop offset="95%" stopColor={STROKE_COLOR} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" className="stroke-gov-gray-200 dark:stroke-slate-600" />
          <XAxis
            dataKey="hour"
            tick={{ fill: 'currentColor', fontSize: 11 }}
            className="text-gov-gray-500 dark:text-dark-muted"
          />
          <YAxis
            tick={{ fill: 'currentColor', fontSize: 11 }}
            className="text-gov-gray-500 dark:text-dark-muted"
            tickFormatter={(v) => `${v} ms`}
          />
          <Tooltip
            formatter={(value) => [`${Number(value ?? 0)} ms`, 'Latencia media']}
            contentStyle={{
              backgroundColor: '#1e293b',
              border: '1px solid #334155',
              borderRadius: '8px',
              color: '#f1f5f9',
            }}
          />
          <Area
            type="monotone"
            dataKey="latency"
            stroke={STROKE_COLOR}
            fill="url(#latencyFill)"
            strokeWidth={2}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
