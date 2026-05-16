'use client';

import { ChevronRight, MessageCircle, Mail, MessageSquare, Globe, Monitor, Users } from 'lucide-react';
import { TicketConUrgencia, CanalOrigen } from '@/types';
import { formatearFecha } from '@/lib/utils';
import { UrgencyBadge } from './';
import { StatusBadge } from '../shared';
import RadicadoBadge from '@/components/ticket/RadicadoBadge';

interface TicketRowProps {
  ticket: TicketConUrgencia;
  onRowClick: (idTicket: string) => void;
}

const CanalIcon = ({ canal }: { canal: CanalOrigen }) => {
  switch (canal) {
    case 'WhatsApp': return <MessageCircle size={12} />;
    case 'Email': return <Mail size={12} />;
    case 'Twitter': return <MessageSquare size={12} />;
    case 'Facebook': return <Globe size={12} />;
    case 'Web': return <Monitor size={12} />;
    case 'Presencial': return <Users size={12} />;
    default: return <MessageCircle size={12} />;
  }
};

export default function TicketRow({ ticket, onRowClick }: TicketRowProps) {
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onRowClick(ticket.idTicket);
    }
  };

  return (
    <tr
      role="button"
      tabIndex={0}
      onClick={() => onRowClick(ticket.idTicket)}
      onKeyDown={handleKeyDown}
      className="border-b border-gov-gray-100 dark:border-dark-border hover:bg-gov-gray-50 dark:hover:bg-dark-sidebar/50 cursor-pointer transition-colors duration-150 group"
    >
      {/* 1. Urgency Compact */}
      <td className="py-4 pl-4 w-12 text-center">
        <UrgencyBadge 
          nivelUrgencia={ticket.nivelUrgencia} 
          diasRestantes={ticket.diasRestantes} 
          compact 
        />
      </td>

      {/* 2. ID / Canal */}
      <td className="py-4 px-3 w-40 hidden lg:table-cell">
        <div className="flex flex-col gap-1">
          <RadicadoBadge 
            numeroRadicado={ticket.numeroRadicado} 
            variant="short" 
          />
          <div className="flex items-center gap-1.5 text-[10px] font-bold text-gov-gray-500 dark:text-dark-muted/80 uppercase">
            <CanalIcon canal={ticket.canalOrigen} />
            <span>{ticket.canalOrigen}</span>
          </div>
        </div>
      </td>

      {/* 3. Ciudadano / Tipo */}
      <td className="py-4 px-3 flex-1">
        <div className="flex flex-col">
          <span className="text-sm font-medium text-gov-gray-900 dark:text-dark-text">
            {ticket.nombreCiudadano}
          </span>
          <span className="text-xs text-gov-gray-500 dark:text-dark-muted">
            {ticket.tipoSolicitud}
          </span>
        </div>
      </td>

      {/* 4. Estado */}
      <td className="py-4 px-3">
        <StatusBadge estado={ticket.estado} />
      </td>

      {/* 5. Urgencia Completa */}
      <td className="py-4 px-3 w-36 hidden md:table-cell">
        <UrgencyBadge 
          nivelUrgencia={ticket.nivelUrgencia} 
          diasRestantes={ticket.diasRestantes} 
        />
      </td>

      {/* 6. Fecha Creación */}
      <td className="py-4 px-3 w-32 border-transparent hidden sm:table-cell">
        <span className="text-xs text-gov-gray-500 dark:text-dark-muted font-medium">
          {formatearFecha(ticket.fechaCreacion)}
        </span>
      </td>

      {/* 7. Chevron */}
      <td className="py-4 pr-4 w-8 text-right">
        <ChevronRight size={18} className="text-gov-gray-300 dark:text-dark-border group-hover:text-gov-blue-500 dark:group-hover:text-dark-cyan transition-colors" />
      </td>
    </tr>
  );
}
