import { useState, useMemo, useCallback } from 'react';
import { useTickets } from './useTickets';

export interface Notificacion {
  idTicket: string;
  nombreCiudadano: string;
  tipoSolicitud: string;
  diasRestantes: number;
  nivelUrgencia: 'critico' | 'atencion';
  /** Mensaje legible para el funcionario */
  mensaje: string;
}

interface UseNotificationsReturn {
  notificaciones: Notificacion[];
  totalCriticas: number;
  totalAtencion: number;
  hayVencidos: boolean;
  /** IDs de notificaciones que el usuario marcó como "vistas" en esta sesión */
  vistas: Set<string>;
  marcarComoVista: (idTicket: string) => void;
  marcarTodasVistas: () => void;
}

export function useNotifications(): UseNotificationsReturn {
  const { tickets } = useTickets();
  const [vistas, setVistas] = useState<Set<string>>(new Set());

  const notificaciones = useMemo(() => {
    return tickets
      .filter(t => (t.nivelUrgencia === 'critico' || t.nivelUrgencia === 'atencion') && t.estado !== 'Resuelto')
      .map(t => {
        let mensaje = '';
        if (t.diasRestantes < 0) {
          mensaje = `VENCIDO hace ${Math.abs(t.diasRestantes)} días hábiles`;
        } else if (t.diasRestantes === 0) {
          mensaje = "¡Vence HOY! Respuesta requerida antes de las 5:00 PM";
        } else if (t.diasRestantes === 1) {
          mensaje = "Vence mañana. Solo queda 1 día hábil";
        } else if (t.diasRestantes <= 3) {
          mensaje = `Quedan solo ${t.diasRestantes} días hábiles para responder`;
        } else {
          mensaje = `Plazo en curso: ${t.diasRestantes} días hábiles restantes`;
        }

        return {
          idTicket: t.idTicket,
          nombreCiudadano: t.nombreCiudadano,
          tipoSolicitud: t.tipoSolicitud,
          diasRestantes: t.diasRestantes,
          nivelUrgencia: t.nivelUrgencia as 'critico' | 'atencion',
          mensaje
        };
      })
      .sort((a, b) => {
        // 1. Vencidos primero
        if (a.diasRestantes < 0 && b.diasRestantes >= 0) return -1;
        if (a.diasRestantes >= 0 && b.diasRestantes < 0) return 1;
        
        // 2. Por nivel de urgencia (crítico antes que atención)
        if (a.nivelUrgencia === 'critico' && b.nivelUrgencia === 'atencion') return -1;
        if (a.nivelUrgencia === 'atencion' && b.nivelUrgencia === 'critico') return 1;

        // 3. Por días restantes ascendente
        return a.diasRestantes - b.diasRestantes;
      });
  }, [tickets]);

  const stats = useMemo(() => {
    return {
      totalCriticas: notificaciones.filter(n => n.nivelUrgencia === 'critico').length,
      totalAtencion: notificaciones.filter(n => n.nivelUrgencia === 'atencion').length,
      hayVencidos: notificaciones.some(n => n.diasRestantes < 0)
    };
  }, [notificaciones]);

  const marcarComoVista = useCallback((idTicket: string) => {
    setVistas(prev => {
      const next = new Set(prev);
      next.add(idTicket);
      return next;
    });
  }, []);

  const marcarTodasVistas = useCallback(() => {
    setVistas(new Set(notificaciones.map(n => n.idTicket)));
  }, [notificaciones]);

  return {
    notificaciones,
    totalCriticas: stats.totalCriticas,
    totalAtencion: stats.totalAtencion,
    hayVencidos: stats.hayVencidos,
    vistas,
    marcarComoVista,
    marcarTodasVistas
  };
}
