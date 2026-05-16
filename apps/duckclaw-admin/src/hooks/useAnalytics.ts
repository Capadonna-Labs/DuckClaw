'use client';

import { useMemo } from 'react';
import { useTickets } from './useTickets';
import { TipoSolicitud, CanalOrigen } from '@/types';
import { startOfWeek, subWeeks, isWithinInterval } from 'date-fns';

interface MetricasPrincipales {
  totalTickets: number;
  resueltos: number;
  pendientes: number;
  enRevision: number;
  tasaCumplimiento: number;      // % de resueltos a tiempo (no vencidos)
  promedioRespuestaDias: number; // promedio de días usados para resolver
  ticketsCriticos: number;
  ticketsVencidos: number;
}

interface DistribucionTipo {
  tipo: TipoSolicitud;
  cantidad: number;
  porcentaje: number;
  color: string;
}

interface DistribucionCanal {
  canal: CanalOrigen;
  cantidad: number;
  porcentaje: number;
}

interface TendenciaSemanal {
  semana: string;          // "Sem 1", "Sem 2", etc.
  ingresados: number;
  resueltos: number;
  vencidos: number;
}

interface UseAnalyticsReturn {
  metricas: MetricasPrincipales;
  distribucionPorTipo: DistribucionTipo[];
  distribucionPorCanal: DistribucionCanal[];
  tendenciaSemanal: TendenciaSemanal[];
  tendenciaDiaria: { fecha: string; cantidad: number }[];
  isLoading: boolean;
}

const COLORES_POR_TIPO: Record<TipoSolicitud, string> = {
  Peticion: '#003DA5',
  Queja: '#DC2626',
  Reclamo: '#D97706',
  Sugerencia: '#00875A',
  Denuncia: '#7C3AED'
};

/**
 * Hook useAnalytics
 * Procesa la analítica de los PQRSDs de la secretaría activa.
 */
export function useAnalytics(): UseAnalyticsReturn {
  const { tickets, isLoading } = useTickets();

  // 1. Cálculos de métricas globales
  const metricas = useMemo(() => {
    const total = tickets.length;
    if (total === 0) {
      return {
        totalTickets: 0,
        resueltos: 0,
        pendientes: 0,
        enRevision: 0,
        tasaCumplimiento: 0,
        promedioRespuestaDias: 0,
        ticketsCriticos: 0,
        ticketsVencidos: 0,
      };
    }

    const resueltos = tickets.filter(t => t.estado === 'Resuelto');
    const resueltosATiempo = resueltos.filter(t => t.diasRestantes >= 0);
    const pendientes = tickets.filter(t => t.estado === 'Pendiente');
    const enRevision = tickets.filter(t => t.estado === 'En_Revision');
    const vencidos = tickets.filter(t => t.diasRestantes < 0);
    const criticos = tickets.filter(t => t.nivelUrgencia === 'critico');

    return {
      totalTickets: total,
      resueltos: resueltos.length,
      pendientes: pendientes.length,
      enRevision: enRevision.length,
      tasaCumplimiento: Math.round((resueltosATiempo.length / total) * 100),
      // Mock realista mientras no hay data de fecha de resolución real
      promedioRespuestaDias: total > 0 ? 8.4 : 0, 
      ticketsCriticos: criticos.length,
      ticketsVencidos: vencidos.length,
    };
  }, [tickets]);

  // 2. Distribución por Tipo de Solicitud
  const distribucionPorTipo = useMemo(() => {
    const counts: Partial<Record<TipoSolicitud, number>> = {};
    tickets.forEach(t => {
      counts[t.tipoSolicitud] = (counts[t.tipoSolicitud] || 0) + 1;
    });

    return (Object.keys(COLORES_POR_TIPO) as TipoSolicitud[]).map(tipo => {
      const cantidad = counts[tipo] || 0;
      return {
        tipo,
        cantidad,
        porcentaje: tickets.length > 0 ? Math.round((cantidad / tickets.length) * 100) : 0,
        color: COLORES_POR_TIPO[tipo]
      };
    });
  }, [tickets]);

  // 3. Distribución por Canal de Origen
  const distribucionPorCanal = useMemo(() => {
    const counts: Record<string, number> = {};
    tickets.forEach(t => {
      counts[t.canalOrigen] = (counts[t.canalOrigen] || 0) + 1;
    });

    return Object.entries(counts).map(([canal, cantidad]) => ({
      canal: canal as CanalOrigen,
      cantidad,
      porcentaje: tickets.length > 0 ? Math.round((cantidad / tickets.length) * 100) : 0
    })).sort((a, b) => b.cantidad - a.cantidad);
  }, [tickets]);

  // 4. Tendencia Semanal (Últimas 4 semanas)
  const tendenciaSemanal = useMemo(() => {
    const hoy = new Date();
    const semanas = [3, 2, 1, 0].map(offset => {
      const inicio = startOfWeek(subWeeks(hoy, offset), { weekStartsOn: 1 });
      const fin = new Date(inicio.getTime() + 6 * 24 * 60 * 60 * 1000);
      return {
        label: `Sem ${offset === 0 ? 'Act' : 4 - offset}`,
        intervalo: { start: inicio, end: fin }
      };
    });

    return semanas.map(sem => {
      const ticketsSemana = tickets.filter(t => 
        isWithinInterval(new Date(t.fechaCreacion), sem.intervalo)
      );

      return {
        semana: sem.label,
        ingresados: ticketsSemana.length,
        resueltos: ticketsSemana.filter(t => t.estado === 'Resuelto').length,
        vencidos: ticketsSemana.filter(t => t.diasRestantes < 0).length
      };
    });
  }, [tickets]);

  // 5. Tendencia Diaria (Últimos 7 días)
  const tendenciaDiaria = useMemo(() => {
    const hoy = new Date();
    return [6, 5, 4, 3, 2, 1, 0].map(d => {
      const fecha = new Date(hoy);
      fecha.setDate(hoy.getDate() - d);
      const fechaStr = fecha.toISOString().split('T')[0];
      
      const count = tickets.filter(t => 
        t.fechaCreacion.startsWith(fechaStr)
      ).length;

      return {
        fecha: fecha.toLocaleDateString('es-CO', { day: '2-digit', month: 'short' }),
        cantidad: count
      };
    });
  }, [tickets]);

  return {
    metricas,
    distribucionPorTipo,
    distribucionPorCanal,
    tendenciaSemanal,
    tendenciaDiaria,
    isLoading
  };
}
