'use client';

import { useEffect, useState } from 'react';
import { Search, X, RefreshCw } from 'lucide-react';
import { useTickets } from '@/hooks/useTickets';
import { useFilterStore } from '@/store/filterStore';
import { TicketEstado, TipoSolicitud, NivelUrgencia } from '@/types';
import { cn } from '@/lib/utils';

export default function FilterBar() {
  const {
    estadoFilter,
    tipoFilter,
    urgenciaFilter,
    searchQuery,
    setEstadoFilter,
    setTipoFilter,
    setUrgenciaFilter,
    setSearchQuery,
    resetFilters,
  } = useFilterStore();
  const { refetch } = useTickets();
  const [isRefreshing, setIsRefreshing] = useState(false);

  const [localSearch, setLocalSearch] = useState(searchQuery);

  // Sincronizar localSearch cuando el store cambie (ej. al resetear)
  useEffect(() => {
    setLocalSearch(searchQuery);
  }, [searchQuery]);

  // Manejo de Debounce para la búsqueda
  useEffect(() => {
    const handler = setTimeout(() => {
      setSearchQuery(localSearch);
    }, 300);

    return () => clearTimeout(handler);
  }, [localSearch, setSearchQuery]);

  const isAnyFilterActive = 
    estadoFilter !== 'Todos' || 
    tipoFilter !== 'Todos' || 
    urgenciaFilter !== 'Todos' || 
    searchQuery !== '';

  const selectClass = "text-sm border border-gov-gray-300 dark:border-dark-border rounded-lg px-3 py-2 bg-white dark:bg-dark-surface focus:outline-none focus:ring-2 focus:ring-gov-blue-500 dark:focus:ring-dark-cyan text-gov-gray-900 dark:text-dark-text";

  return (
    <div className="flex flex-col lg:flex-row gap-4 items-stretch lg:items-center p-4 bg-white dark:bg-dark-surface rounded-xl border border-gov-gray-100 dark:border-dark-border shadow-sm mb-6 transition-all">
      
      {/* 1. BUSCADOR (Prioridad en móvil) */}
      <div className="flex-1 relative order-1 lg:order-none">
        <label htmlFor="search-input" className="sr-only">
          Buscar ciudadano o contenido
        </label>
        <div className="absolute left-3 top-1/2 -translate-y-1/2 text-gov-gray-400">
          <Search size={18} />
        </div>
        <input
          id="search-input"
          type="text"
          value={localSearch}
          onChange={(e) => setLocalSearch(e.target.value)}
          placeholder="Buscar por ciudadano o contenido..."
          className="w-full pl-10 pr-4 py-2.5 lg:py-2 text-sm border border-gov-gray-300 dark:border-dark-border rounded-lg focus:outline-none focus:ring-2 focus:ring-gov-blue-500 dark:focus:ring-dark-cyan focus:border-transparent bg-white dark:bg-dark-surface text-gov-gray-900 dark:text-dark-text shadow-sm"
        />
      </div>

      {/* 2. GRUPO DE FILTROS (Grid en móvil, flex en desktop) */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:flex items-center gap-3 lg:gap-4 order-2 lg:order-none">
        {/* SELECT ESTADO */}
        <div className="flex flex-col lg:flex-row lg:items-center gap-1.5 lg:gap-2">
          <label htmlFor="estado-select" className="text-[10px] font-bold text-gov-gray-400 dark:text-dark-muted uppercase tracking-wider pl-1 lg:pl-0">
            Estado
          </label>
          <select
            id="estado-select"
            value={estadoFilter}
            onChange={(e) => setEstadoFilter(e.target.value as TicketEstado | 'Todos')}
            className={cn(selectClass, "w-full lg:w-36")}
          >
            <option value="Todos">Todos</option>
            <option value="Pendiente">Pendiente</option>
            <option value="En_Revision">En Revisión</option>
            <option value="Resuelto">Resuelto</option>
          </select>
        </div>

        {/* SELECT TIPO */}
        <div className="flex flex-col lg:flex-row lg:items-center gap-1.5 lg:gap-2">
          <label htmlFor="tipo-select" className="text-[10px] font-bold text-gov-gray-400 dark:text-dark-muted uppercase tracking-wider pl-1 lg:pl-0">
            Tipo
          </label>
          <select
            id="tipo-select"
            value={tipoFilter}
            onChange={(e) => setTipoFilter(e.target.value as TipoSolicitud | 'Todos')}
            className={cn(selectClass, "w-full lg:w-36")}
          >
            <option value="Todos">Todos</option>
            <option value="Peticion">Petición</option>
            <option value="Queja">Queja</option>
            <option value="Reclamo">Reclamo</option>
            <option value="Sugerencia">Sugerencia</option>
            <option value="Denuncia">Denuncia</option>
          </select>
        </div>

        {/* SELECT URGENCIA */}
        <div className="flex flex-col lg:flex-row lg:items-center gap-1.5 lg:gap-2 col-span-2 sm:col-span-1">
          <label htmlFor="urgencia-select" className="text-[10px] font-bold text-gov-gray-400 dark:text-dark-muted uppercase tracking-wider pl-1 lg:pl-0">
            Urgencia
          </label>
          <select
            id="urgencia-select"
            value={urgenciaFilter}
            onChange={(e) => setUrgenciaFilter(e.target.value as NivelUrgencia | 'Todos')}
            className={cn(selectClass, "w-full lg:w-36")}
          >
            <option value="Todos">Todas</option>
            <option value="critico">🔴 Crítico</option>
            <option value="atencion">🟡 Atención</option>
            <option value="seguro">🟢 Seguro</option>
          </select>
        </div>
      </div>

      {/* 3. ACCIONES (Bottom en móvil, Right en desktop) */}
      <div className="flex items-center gap-3 pt-2 lg:pt-0 border-t lg:border-t-0 border-gov-gray-100 dark:border-dark-border order-3 lg:order-none justify-between lg:justify-end">
        {isAnyFilterActive && (
          <button
            onClick={resetFilters}
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-bold text-sem-red hover:bg-sem-red-bg rounded-lg transition-colors border border-transparent"
            aria-label="Limpiar todos los filtros"
          >
            <X size={14} />
            <span className="lg:hidden xl:inline">Limpiar</span>
          </button>
        )}

        <button
          onClick={async () => {
            setIsRefreshing(true);
            await refetch();
            setTimeout(() => setIsRefreshing(false), 500);
          }}
          className="flex-1 lg:flex-none flex items-center justify-center gap-2 px-4 py-2 text-xs font-bold text-gov-blue-700 dark:text-dark-cyan bg-gov-blue-50 dark:bg-dark-accent/10 rounded-lg transition-all border border-gov-blue-200 dark:border-dark-cyan/20 hover:bg-gov-blue-100 dark:hover:bg-dark-accent/20 active:scale-95"
          title="Sincronizar con el servidor de correos"
        >
          <RefreshCw size={14} className={isRefreshing ? 'animate-spin' : ''} />
          <span>Sincronizar</span>
        </button>
      </div>
    </div>
  );
}
