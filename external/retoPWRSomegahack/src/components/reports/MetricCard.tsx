'use client';

import { TrendingUp, TrendingDown } from 'lucide-react';
import { cn } from '@/lib/utils';

interface MetricCardProps {
  titulo: string;
  valor: string | number;
  subtitulo?: string;
  icono: React.ReactNode;
  tendencia?: { valor: number; positivo: boolean };
  colorIcono?: string;
  bgIcono?: string;
}

export default function MetricCard({
  titulo,
  valor,
  subtitulo,
  icono,
  tendencia,
  colorIcono = "text-gov-blue-700",
  bgIcono = "bg-gov-blue-100"
}: MetricCardProps) {
  return (
    <div className="bg-white dark:bg-dark-surface rounded-2xl border border-gov-gray-100 dark:border-dark-border p-5 shadow-sm hover:shadow-md transition-all group">
      <div className="flex items-center justify-between mb-4">
        <div className={cn(
          "p-2.5 rounded-xl transition-transform group-hover:scale-110 duration-300",
          bgIcono,
          colorIcono
        )}>
          {icono}
        </div>
        
        {tendencia && (
          <div className={cn(
            "flex items-center gap-1 text-[10px] font-black px-2 py-1 rounded-full",
            tendencia.positivo 
              ? "bg-sem-green-bg dark:bg-sem-green/10 text-sem-green border border-sem-green/20" 
              : "bg-sem-red-bg dark:bg-sem-red/10 text-sem-red border border-sem-red/20"
          )}>
            {tendencia.positivo ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
            {tendencia.positivo ? '+' : '-'}{tendencia.valor}%
          </div>
        )}
      </div>

      <div className="space-y-1">
        <p className="text-[10px] sm:text-xs font-bold text-gov-gray-500 dark:text-dark-muted uppercase tracking-widest">{titulo}</p>
        <div className="flex items-baseline gap-2">
          <h3 className="text-2xl sm:text-3xl font-black text-gov-gray-900 dark:text-dark-text tracking-tighter">
            {valor}
          </h3>
          {subtitulo && (
            <span className="text-[10px] font-medium text-gov-gray-400 dark:text-dark-muted/70 lowercase italic">
              {subtitulo}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
