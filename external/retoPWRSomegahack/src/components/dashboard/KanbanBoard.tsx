'use client';

import { useState, useMemo, useEffect } from 'react';
import {
  DndContext,
  DragEndEvent,
  DragOverEvent,
  DragStartEvent,
  PointerSensor,
  useSensor,
  useSensors,
  DragOverlay,
  closestCorners,
} from '@dnd-kit/core';
import { 
  SortableContext, 
  verticalListSortingStrategy, 
  useSortable
} from '@dnd-kit/sortable';
import { useDroppable } from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import { useTickets } from '@/hooks/useTickets';
import { useIdSecretariaActivo } from '@/store/authStore';
import { TicketConUrgencia, TicketEstado } from '@/types';
import { UrgencyBadge } from './';
import { formatearFecha, truncarTexto } from '@/lib/utils';
import { useRouter } from 'next/navigation';
import { GripVertical, MessageCircle } from 'lucide-react';
import { actualizarEstadoTicket } from '@/services/ticketService';
import { useDataMode } from '@/store/authStore';

const COLUMNAS: { id: TicketEstado; label: string; color: string }[] = [
  { id: 'Pendiente', label: 'Pendiente', color: 'border-t-gov-blue-500' },
  { id: 'En_Revision', label: 'En Revisión', color: 'border-t-gov-gold-500' },
  { id: 'Resuelto', label: 'Resuelto', color: 'border-t-sem-green' },
];

/**
 * KanbanCard - Item arrastrable
 */
function KanbanCard({ ticket, isDragging }: { ticket: TicketConUrgencia; isDragging?: boolean }) {
  const router = useRouter();
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
  } = useSortable({ 
    id: ticket.idTicket,
    data: {
      type: 'Ticket',
      ticket,
    }
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const handleCardClick = () => {
    // Evitar navegación si se está arrastrando
    if (transform) return;
    router.push(`/ticket/${ticket.idTicket}`);
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        "bg-white dark:bg-dark-surface rounded-xl border border-gov-gray-100 dark:border-dark-border p-4 shadow-sm select-none transition-shadow relative group",
        isDragging ? "opacity-50 shadow-2xl ring-2 ring-gov-blue-500 z-50" : "hover:shadow-md cursor-grab active:cursor-grabbing"
      )}
      onClick={handleCardClick}
    >
      <div className="flex justify-between items-start mb-3">
        <div className="flex items-center gap-2">
          <UrgencyBadge nivelUrgencia={ticket.nivelUrgencia} diasRestantes={ticket.diasRestantes} compact />
          <span className="text-[10px] font-mono font-bold text-gov-gray-400 uppercase tracking-tighter">
            {ticket.idTicket}
          </span>
        </div>
        <div {...attributes} {...listeners} className="text-gov-gray-300 dark:text-dark-muted hover:text-gov-gray-500 dark:hover:text-dark-text transition-colors p-1">
          <GripVertical size={16} />
        </div>
      </div>

      <h3 className="text-sm font-bold text-gov-gray-900 dark:text-dark-text leading-tight mb-1">
        {truncarTexto(ticket.nombreCiudadano, 28)}
      </h3>
      
      <div className="flex items-center gap-2 mb-3">
        <span className="text-[10px] font-bold text-gov-gray-500 uppercase tracking-tight">
          {ticket.tipoSolicitud}
        </span>
        <span className="text-gov-gray-200">•</span>
        <div className="flex items-center gap-1 text-[10px] text-gov-gray-400 font-medium">
          <MessageCircle size={10} />
          {ticket.canalOrigen}
        </div>
      </div>

      <div className="flex justify-between items-center pt-3 border-t border-gov-gray-50 dark:border-dark-border">
        <span className="text-[10px] font-medium text-gov-gray-400">
          {formatearFecha(ticket.fechaCreacion)}
        </span>
        <UrgencyBadge nivelUrgencia={ticket.nivelUrgencia} diasRestantes={ticket.diasRestantes} />
      </div>
    </div>
  );
}

/**
 * KanbanColumn - Contenedor de destino
 */
function KanbanColumn({ 
  columna, 
  tickets 
}: { 
  columna: typeof COLUMNAS[0]; 
  tickets: TicketConUrgencia[] 
}) {
  const { setNodeRef } = useDroppable({
    id: columna.id,
  });

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-4 px-2">
        <div className="flex items-center gap-2">
           <h3 className="text-sm font-bold text-gov-gray-800 dark:text-dark-text uppercase tracking-wide">
            {columna.label}
          </h3>
          <span className="bg-gov-gray-200 dark:bg-dark-border text-gov-gray-600 dark:text-dark-text text-[10px] font-black px-2 py-0.5 rounded-full">
            {tickets.length}
          </span>
        </div>
      </div>

      <div
        ref={setNodeRef}
        className={cn(
          "flex flex-col gap-3 bg-gov-gray-50/50 dark:bg-dark-surface/50 rounded-2xl p-3 min-h-[500px] border-t-4 transition-colors duration-200",
          columna.color
        )}
      >
        <SortableContext 
          id={columna.id}
          items={tickets.map(t => t.idTicket)} 
          strategy={verticalListSortingStrategy}
        >
          {tickets.map((ticket) => (
            <KanbanCard key={ticket.idTicket} ticket={ticket} />
          ))}
        </SortableContext>
      </div>
    </div>
  );
}

/**
 * MÓDULO PRINCIPAL: KanbanBoard
 */
export default function KanbanBoard() {
  const { tickets, refetch } = useTickets();
  const idSecretaria = useIdSecretariaActivo();
  const [items, setItems] = useState<Record<TicketEstado, TicketConUrgencia[]>>({
    Pendiente: [],
    En_Revision: [],
    Resuelto: [],
  });
  const [activeId, setActiveId] = useState<string | null>(null);

  // Sincronizar estado local con tickets del hook (filtrados/buscados)
  useEffect(() => {
    const grouped = tickets.reduce((acc, ticket) => {
      if (!acc[ticket.estado]) acc[ticket.estado] = [];
      acc[ticket.estado].push(ticket);
      return acc;
    }, {
      Pendiente: [],
      En_Revision: [],
      Resuelto: [],
    } as Record<TicketEstado, TicketConUrgencia[]>);
    
    setItems(grouped);
  }, [tickets]);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8, // Previene drag accidental al hacer click
      },
    })
  );

  const activeTicket = useMemo(() => {
    if (!activeId) return null;
    return tickets.find(t => t.idTicket === activeId);
  }, [activeId, tickets]);

  function handleDragStart(event: DragStartEvent) {
    setActiveId(event.active.id as string);
  }

  function handleDragOver(event: DragOverEvent) {
    const { active, over } = event;
    if (!over) return;

    const activeId = active.id;
    const overId = over.id;

    // Obtener las columnas de origen y destino
    const activeColumn = Object.keys(items).find(key => 
      items[key as TicketEstado].some(t => t.idTicket === activeId)
    ) as TicketEstado;
    
    // El 'overId' puede ser un ID de ticket o un ID de columna
    const overColumn = (COLUMNAS.some(c => c.id === overId) 
      ? overId 
      : Object.keys(items).find(key => 
          items[key as TicketEstado].some(t => t.idTicket === overId)
        )
    ) as TicketEstado;

    if (!activeColumn || !overColumn || activeColumn === overColumn) return;

    setItems(prev => {
      const activeItems = [...prev[activeColumn]];
      const overItems = [...prev[overColumn]];

      const activeIndex = activeItems.findIndex(t => t.idTicket === activeId);
      const [movedTicket] = activeItems.splice(activeIndex, 1);
      
      // Actualizar el estado interno del ticket movido
      const updatedTicket = { ...movedTicket, estado: overColumn };
      overItems.push(updatedTicket);

      return {
        ...prev,
        [activeColumn]: activeItems,
        [overColumn]: overItems,
      };
    });
  }

  const dataMode = useDataMode();

  async function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    setActiveId(null);

    if (!over) return;

    const idTicket = active.id as string;
    const overId = over.id;

    // Determinar estado final
    const finalState = (COLUMNAS.some(c => c.id === overId)
      ? overId
      : Object.keys(items).find(key => 
          items[key as TicketEstado].some(t => t.idTicket === idTicket)
        )
    ) as TicketEstado;

    if (finalState && idSecretaria) {
      try {
        await actualizarEstadoTicket(idTicket, finalState, idSecretaria, dataMode);
        refetch(); // Sincronizar con el store global
      } catch (err) {
        console.error("Error al persistir cambio de estado:", err);
      }
    }
  }

  return (
    <div className="w-full animate-in fade-in duration-500">
      <DndContext
        sensors={sensors}
        collisionDetection={closestCorners}
        onDragStart={handleDragStart}
        onDragOver={handleDragOver}
        onDragEnd={handleDragEnd}
      >
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {COLUMNAS.map((col) => (
            <KanbanColumn 
              key={col.id} 
              columna={col} 
              tickets={items[col.id]} 
            />
          ))}
        </div>

        <DragOverlay>
          {activeId && activeTicket ? (
            <KanbanCard ticket={activeTicket} isDragging />
          ) : null}
        </DragOverlay>
      </DndContext>
    </div>
  );
}

// Helper para concatenar clases
function cn(...classes: (string | boolean | undefined)[]) {
  return classes.filter(Boolean).join(' ');
}
