import { differenceInBusinessDays, parseISO } from 'date-fns';
import { NivelUrgencia, TicketConUrgencia, Ticket } from '@/types';

/**
 * Calcula los días hábiles (lunes–viernes) que faltan hasta la fechaLimite.
 * Usa date-fns differenceInBusinessDays con la fecha actual.
 * Si fechaLimite ya pasó, retorna un número negativo.
 * @param fechaLimite - ISO 8601 string de la fecha límite del ticket
 * @returns número de días hábiles restantes (puede ser negativo si está vencido)
 */
export function calcularDiasHabilesRestantes(fechaLimite: string): number {
  const targetDate = parseISO(fechaLimite);
  const now = new Date();
  
  // differenceInBusinessDays(later, earlier)
  return differenceInBusinessDays(targetDate, now);
}

/**
 * Determina el nivel de semáforo según los días restantes:
 * - 'critico'  : diasRestantes <= 3  (ROJO    #DC2626)
 * - 'atencion' : diasRestantes <= 10 (AMARILLO #D97706)
 * - 'seguro'   : diasRestantes > 10  (VERDE   #00875A)
 * Los tickets vencidos (< 0) también son 'critico'.
 */
export function determinarNivelUrgencia(diasRestantes: number): NivelUrgencia {
  if (diasRestantes <= 3) return 'critico';
  if (diasRestantes <= 10) return 'atencion';
  return 'seguro';
}

/**
 * Toma un Ticket plano del backend y retorna un TicketConUrgencia 
 * con diasRestantes y nivelUrgencia calculados.
 * Esta función es el puente entre el contrato DuckDB y la UI.
 */
export function enriquecerTicketConUrgencia(ticket: Ticket): TicketConUrgencia {
  const diasRestantes = calcularDiasHabilesRestantes(ticket.fechaLimite);
  const nivelUrgencia = determinarNivelUrgencia(diasRestantes);

  return {
    ...ticket,
    diasRestantes,
    nivelUrgencia,
  };
}

/**
 * Devuelve la configuración visual para un nivel de urgencia dado.
 * Úsala en los componentes para mantener consistencia visual.
 * @returns objeto con: { bgColor, textColor, borderColor, label }
 */
export function getUrgencyConfig(nivel: NivelUrgencia): {
  bgColor: string;
  textColor: string;
  borderColor: string;
  label: string;
} {
  const configs = {
    critico: {
      bgColor: 'bg-sem-red-bg dark:bg-sem-red/10',
      textColor: 'text-sem-red',
      borderColor: 'border-sem-red dark:border-sem-red/20',
      label: 'CRÍTICO'
    },
    atencion: {
      bgColor: 'bg-sem-yellow-bg dark:bg-sem-yellow/10',
      textColor: 'text-sem-yellow',
      borderColor: 'border-sem-yellow dark:border-sem-yellow/20',
      label: 'ATENCIÓN'
    },
    seguro: {
      bgColor: 'bg-sem-green-bg dark:bg-sem-green/10',
      textColor: 'text-sem-green',
      borderColor: 'border-sem-green dark:border-sem-green/20',
      label: 'SEGURO'
    }
  };

  return configs[nivel];
}
