import { create } from 'zustand';
import { TicketEstado, TipoSolicitud, NivelUrgencia } from '@/types';

interface FilterState {
  estadoFilter: TicketEstado | 'Todos';
  tipoFilter: TipoSolicitud | 'Todos';
  urgenciaFilter: NivelUrgencia | 'Todos';
  searchQuery: string;
  
  // Acciones
  setEstadoFilter: (estado: TicketEstado | 'Todos') => void;
  setTipoFilter: (tipo: TipoSolicitud | 'Todos') => void;
  setUrgenciaFilter: (urgencia: NivelUrgencia | 'Todos') => void;
  setSearchQuery: (query: string) => void;
  resetFilters: () => void;
}

export const useFilterStore = create<FilterState>((set) => ({
  // Estado inicial
  estadoFilter: 'Todos',
  tipoFilter: 'Todos',
  urgenciaFilter: 'Todos',
  searchQuery: '',

  setEstadoFilter: (estado) => set({ estadoFilter: estado }),
  setTipoFilter: (tipo) => set({ tipoFilter: tipo }),
  setUrgenciaFilter: (urgencia) => set({ urgenciaFilter: urgencia }),
  setSearchQuery: (query) => set({ searchQuery: query }),
  
  resetFilters: () => set({
    estadoFilter: 'Todos',
    tipoFilter: 'Todos',
    urgenciaFilter: 'Todos',
    searchQuery: '',
  }),
}));
