'use client';

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { OverviewActivityRow } from '@/types/admin';

const SUCCESS_COLOR = '#60a5fa';
const FAILED_COLOR = '#ef4444';

type Props = {
  data: OverviewActivityRow[];
};

export default function ActivityChart({ data }: Props) {
  if (!data.length) {
    return (
      <p className="text-sm text-gov-gray-500 dark:text-dark-muted py-8 text-center">
        Sin datos en el periodo
      </p>
    );
  }

  const chartData = data.map((row) => ({
    worker: row.worker_id,
    Éxitos: row.success_count,
    Fallos: row.failed_count,
  }));

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-gov-gray-200 dark:stroke-slate-700" />
          <XAxis
            dataKey="worker"
            tick={{ fill: 'currentColor', fontSize: 11 }}
            className="text-gov-gray-500 dark:text-dark-muted"
          />
          <YAxis
            allowDecimals={false}
            tick={{ fill: 'currentColor', fontSize: 11 }}
            className="text-gov-gray-500 dark:text-dark-muted"
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1e293b',
              border: '1px solid #334155',
              borderRadius: '8px',
              color: '#f1f5f9',
            }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="Éxitos" stackId="a" fill={SUCCESS_COLOR} radius={[0, 0, 0, 0]} />
          <Bar dataKey="Fallos" stackId="a" fill={FAILED_COLOR} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
