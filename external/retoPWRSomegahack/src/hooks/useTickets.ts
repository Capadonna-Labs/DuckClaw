import { useState, useEffect, useCallback, useMemo } from 'react';
import { useIdSecretariaActivo, useDataMode } from '@/store/authStore';
import { useFilterStore } from '@/store/filterStore';
import { getTicketsBySecretaria } from '@/services/ticketService';
import { enriquecerTicketConUrgencia } from '@/lib/urgency';
import { TicketConUrgencia, TicketsFilter } from '@/types';

interface UseTicketsReturn {
  tickets: TicketConUrgencia[];
  isLoading: boolean;
  error: string | null;
  totalTickets: number;
  ticketsCriticos: number; // count de nivelUrgencia === 'critico'
  refetch: () => void;
}

export function useTickets(): UseTicketsReturn {
  const [tickets, setTickets] = useState<TicketConUrgencia[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const idSecretaria = useIdSecretariaActivo();
  const dataMode = useDataMode();
  const { 
    estadoFilter, 
    tipoFilter, 
    urgenciaFilter, 
    searchQuery 
  } = useFilterStore();

  const fetchTickets = useCallback(async () => {
    if (!idSecretaria) {
      setTickets([]);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);

    const filters: TicketsFilter = {
      estado: estadoFilter,
      tipoSolicitud: tipoFilter,
      nivelUrgencia: urgenciaFilter,
      searchQuery: searchQuery,
    };

    try {
      const response = await getTicketsBySecretaria(idSecretaria, dataMode, filters);

      if (response.error) {
        setError(response.error);
        setTickets([]);
      } else {
        // 1. Enriquecer tickets con lógica de urgencia
        const enrichedTickets = response.data.map(enriquecerTicketConUrgencia);

        // 2. Filtrar por nivelUrgencia si el filtro está activo (el servicio mock no filtra por nivelUrgencia directamente)
        let filteredByUrgencia = enrichedTickets;
        if (urgenciaFilter !== 'Todos') {
          filteredByUrgencia = enrichedTickets.filter(t => t.nivelUrgencia === urgenciaFilter);
        }

        // 3. Ordenar: Críticos primero, luego por días restantes ASC
        const sortedTickets = filteredByUrgencia.sort((a, b) => {
          const priority: Record<string, number> = { critico: 1, atencion: 2, seguro: 3 };
          
          if (priority[a.nivelUrgencia] !== priority[b.nivelUrgencia]) {
            return priority[a.nivelUrgencia] - priority[b.nivelUrgencia];
          }
          
          return a.diasRestantes - b.diasRestantes;
        });

        setTickets(sortedTickets);
      }
    } catch (err) {
      setError('Error inesperado al cargar los tickets');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  }, [idSecretaria, dataMode, estadoFilter, tipoFilter, urgenciaFilter, searchQuery]);

  // Refrescar automáticamente cuando los filtros cambian
  useEffect(() => {
    fetchTickets();
  }, [fetchTickets]);

  // Cálculos derivados memorizados
  const stats = useMemo(() => {
    return {
      totalTickets: tickets.length,
      ticketsCriticos: tickets.filter(t => t.nivelUrgencia === 'critico').length
    };
  }, [tickets]);

  return {
    tickets,
    isLoading,
    error,
    totalTickets: stats.totalTickets,
    ticketsCriticos: stats.ticketsCriticos,
    refetch: fetchTickets,
  };
}
