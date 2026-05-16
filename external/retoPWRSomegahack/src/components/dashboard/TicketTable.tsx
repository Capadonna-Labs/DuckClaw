'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTickets } from '@/hooks/useTickets';
import { FilterBar, TicketRow, KanbanBoard } from './';
import { SkeletonRow, EmptyState } from '@/components/shared';
import { AlertTriangle, LayoutGrid, List } from 'lucide-react';
import { cn } from '@/lib/utils';

export default function TicketTable() {
  const router = useRouter();
  const [vista, setVista] = useState<'tabla' | 'kanban'>('tabla');
  const { 
    tickets, 
    isLoading, 
    error, 
    totalTickets, 
    ticketsCriticos 
  } = useTickets();

  const handleRowClick = (idTicket: string) => {
    router.push(`/ticket/${idTicket}`);
  };

  return (
    <div className="w-full">
      {/* Selector de Vista (Tabla / Kanban) */}
      <div className="flex justify-end mb-4">
        <div className="inline-flex p-1 bg-gov-gray-100 dark:bg-dark-surface rounded-xl border border-gov-gray-200 dark:border-dark-border shadow-inner">
          <button
            onClick={() => setVista('tabla')}
            className={cn(
              "flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all",
              vista === 'tabla' 
                ? "bg-white dark:bg-dark-border text-gov-blue-700 dark:text-dark-cyan shadow-sm" 
                : "text-gov-gray-500 dark:text-dark-muted hover:text-gov-gray-700 dark:hover:text-dark-text"
            )}
          >
            <List size={14} />
            Vista Tabla
          </button>
          <button
            onClick={() => setVista('kanban')}
            className={cn(
              "flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all",
              vista === 'kanban' 
                ? "bg-white dark:bg-dark-border text-gov-blue-700 dark:text-dark-cyan shadow-sm" 
                : "text-gov-gray-500 dark:text-dark-muted hover:text-gov-gray-700 dark:hover:text-dark-text"
            )}
          >
            <LayoutGrid size={14} />
            Vista Kanban
          </button>
        </div>
      </div>

      {/* 1. FilterBar */}
      <FilterBar />

      {/* 2. Cabecera de stats */}
      <div className="flex items-center justify-between mb-4 px-1">
        <div className="text-sm text-gov-gray-500 font-medium dark:text-dark-muted">
          <span className="text-gov-gray-900 font-bold dark:text-dark-text">{totalTickets}</span> tickets en tu bandeja
        </div>
        
        {ticketsCriticos > 0 && (
          <div className="flex items-center gap-2 bg-sem-red-bg px-3 py-1 rounded-lg border border-sem-red/20 shadow-sm animate-pulse dark:bg-sem-red/10">
            <AlertTriangle size={14} className="text-sem-red" />
            <span className="text-xs font-bold text-sem-red uppercase tracking-wider">
              {ticketsCriticos} críticos requieren atención
            </span>
          </div>
        )}
      </div>

      {/* 3. Contenido Principal (Tabla o Kanban) */}
      {vista === 'tabla' ? (
        <div className="bg-white rounded-xl border border-gov-gray-100 shadow-sm overflow-hidden dark:bg-dark-surface dark:border-dark-border">
          <div className="overflow-x-auto overflow-y-hidden">
            <table className="w-full border-collapse text-left min-w-[600px] md:min-w-0">
              <thead className="bg-gov-gray-50 text-[10px] sm:text-xs font-bold text-gov-gray-500 uppercase tracking-widest border-b border-gov-gray-100 dark:bg-dark-sidebar dark:border-dark-border dark:text-dark-muted">
                <tr>
                  <th className="py-4 pl-4 w-12"></th>
                  <th className="py-4 px-3 w-40 hidden lg:table-cell">ID / Canal</th>
                  <th className="py-4 px-3">Ciudadano / Tipo</th>
                  <th className="py-4 px-3">Estado</th>
                  <th className="py-4 px-3 w-36 hidden md:table-cell">Urgencia</th>
                  <th className="py-4 px-3 w-32 hidden sm:table-cell">Fecha</th>
                  <th className="py-4 pr-4 w-8"></th>
                </tr>
              </thead>
            <tbody className="divide-y divide-gov-gray-100 dark:divide-dark-border">
              {isLoading ? (
                Array.from({ length: 6 }).map((_, i) => (
                  <SkeletonRow key={`skeleton-${i}`} />
                ))
              ) : error ? (
                <tr>
                  <td colSpan={7}>
                    <EmptyState 
                      variant="error" 
                      customMessage={error} 
                      onAction={() => window.location.reload()}
                      actionLabel="Reintentar"
                    />
                  </td>
                </tr>
              ) : tickets.length === 0 ? (
                <tr>
                  <td colSpan={7}>
                    <EmptyState 
                      variant="filtered" 
                    />
                  </td>
                </tr>
              ) : (
                tickets.map((ticket) => (
                  <TicketRow 
                    key={ticket.idTicket} 
                    ticket={ticket} 
                    onRowClick={handleRowClick} 
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
      ) : (
        <div className="bg-transparent">
          {isLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
               {Array.from({ length: 3 }).map((_, i) => (
                 <div key={i} className="bg-gov-gray-50 dark:bg-dark-surface/50 h-[500px] rounded-2xl animate-pulse" />
               ))}
            </div>
          ) : error ? (
            <div className="bg-white dark:bg-dark-surface rounded-xl border border-gov-gray-100 dark:border-dark-border">
              <EmptyState 
                variant="error" 
                customMessage={error} 
                onAction={() => window.location.reload()}
                actionLabel="Reintentar"
              />
            </div>
          ) : (
            <KanbanBoard />
          )}
        </div>
      )}
      
      {/* Footer informativo opcional */}
      <div className="mt-4 text-center">
        <p className="text-[10px] text-gov-gray-400 dark:text-dark-muted/60 uppercase tracking-tight">
          Datos sincronizados con DuckDB · Medellín Distrito Especial
        </p>
      </div>
    </div>
  );
}
