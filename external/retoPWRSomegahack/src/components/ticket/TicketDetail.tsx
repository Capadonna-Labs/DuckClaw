import { useState } from 'react';
import { 
  MessageSquare, 
  Clock, 
  Sparkles, 
  Calendar, 
  ShieldCheck, 
  Smartphone,
  Info,
  Loader2,
  AlertCircle
} from 'lucide-react';
import { TicketConUrgencia, CanalOrigen, TicketEstado } from '@/types';
import { formatearFecha } from '@/lib/utils';
import { StatusBadge } from '../shared';
import { UrgencyBadge } from '../dashboard';
import { cn } from '@/lib/utils';
import { SECRETARIAS_MOCK } from '@/services/mockData';
import RadicadoBadge from './RadicadoBadge';
import EmailStatusTracker from './EmailStatusTracker';

interface TicketDetailProps {
  ticket: TicketConUrgencia;
  /** Carga del resumen ejecutivo vía gateway (NEXT_PUBLIC_IA_HABILITADA). */
  resumenCargando?: boolean;
  /** Fallo al generar resumen en vivo; el texto mostrado puede ser el mock. */
  resumenError?: string | null;
  onCambiarEstado?: (nuevo: TicketEstado) => void;
  onActualizarCiudadano?: (nombre: string, email: string, telefono?: string) => Promise<void>;
  isSubmitting?: boolean;
}

const CanalEntry = ({ canal }: { canal: CanalOrigen }) => {
  const icons = {
    WhatsApp: Smartphone,
    Email: MessageSquare,
    Twitter: MessageSquare,
    Facebook: MessageSquare,
    Web: MessageSquare,
    Presencial: MessageSquare,
  };
  const Icon = icons[canal] || Info;
  return (
    <div className="flex items-center gap-1.5 text-xs text-gov-gray-500 dark:text-dark-muted font-medium">
      <Icon size={14} className="text-gov-gray-400 dark:text-dark-muted" />
      <span>Recibido vía {canal}</span>
    </div>
  );
};

export default function TicketDetail({
  ticket,
  resumenCargando = false,
  resumenError = null,
  onCambiarEstado,
  onActualizarCiudadano,
  isSubmitting = false,
}: TicketDetailProps) {
  const secretaria = SECRETARIAS_MOCK.find(s => s.idSecretaria === ticket.idSecretaria);
  const [isEditingContact, setIsEditingContact] = useState(false);
  const [editNombre, setEditNombre] = useState(ticket.nombreCiudadano);
  const [editEmail, setEditEmail] = useState(ticket.emailCiudadano || '');
  const [editTelefono] = useState(ticket.telefonoCiudadano || '');
  const [isUpdating, setIsUpdating] = useState(false);

  const handleSaveContact = async () => {
    if (!onActualizarCiudadano) return;
    setIsUpdating(true);
    try {
      await onActualizarCiudadano(editNombre, editEmail, editTelefono);
      setIsEditingContact(false);
    } catch {
      alert('Error al actualizar contacto');
    } finally {
      setIsUpdating(false);
    }
  };

  const isCritical = ticket.nivelUrgencia === 'critico';
  const urgencyColor = isCritical ? 'text-sem-red' : ticket.nivelUrgencia === 'atencion' ? 'text-sem-yellow' : 'text-sem-green';

  return (
    <div className="flex flex-col gap-8">
      {/* ── RADICADO OFICIAL ── */}
      <div
        className="rounded-xl p-4 md:p-6 mb-2 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-lg shadow-gov-blue-900/10"
        style={{ background: 'linear-gradient(135deg, #001E4E 0%, #003DA5 100%)' }}
      >
        <div className="min-w-0">
          <p className="text-gov-cyan-400 text-[9px] md:text-[10px] font-bold uppercase tracking-widest mb-1.5 opacity-80">
            Número de Radicado Oficial · Ley 1755 de 2015
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <RadicadoBadge
              numeroRadicado={ticket.numeroRadicado}
              variant="full"
              size="lg"
              copyable={true}
            />
          </div>
        </div>

        <div className="sm:text-right flex-shrink-0 pt-3 sm:pt-0 border-t sm:border-t-0 border-white/10 min-w-[200px]">
          <div className="flex items-center sm:justify-end gap-2 mb-1">
            <p className="text-white/50 text-[10px] uppercase tracking-wide">Contacto del Ciudadano</p>
            {!isEditingContact && onActualizarCiudadano && (
              <button 
                onClick={() => setIsEditingContact(true)}
                className="text-gov-cyan-400 hover:text-white text-[10px] font-bold uppercase underline decoration-gov-cyan-400/30"
              >
                Editar
              </button>
            )}
          </div>
          
          {isEditingContact ? (
            <div className="space-y-2 mt-2">
              <input 
                type="text"
                className="w-full bg-white/10 border border-white/20 rounded px-2 py-1 text-xs text-white outline-none focus:ring-1 focus:ring-gov-cyan-400"
                placeholder="Nombre"
                value={editNombre}
                onChange={e => setEditNombre(e.target.value)}
              />
              <input 
                type="email"
                className="w-full bg-white/10 border border-white/20 rounded px-2 py-1 text-xs text-white outline-none focus:ring-1 focus:ring-gov-cyan-400"
                placeholder="Email"
                value={editEmail}
                onChange={e => setEditEmail(e.target.value)}
              />
              <div className="flex gap-2">
                <button 
                  disabled={isUpdating}
                  onClick={handleSaveContact}
                  className="flex-1 bg-gov-cyan-400 text-gov-blue-900 text-[10px] font-black uppercase py-1 rounded hover:bg-white transition-colors disabled:opacity-50"
                >
                  {isUpdating ? '...' : 'Guardar'}
                </button>
                <button 
                  onClick={() => setIsEditingContact(false)}
                  className="flex-1 border border-white/20 text-white text-[10px] font-black uppercase py-1 rounded hover:bg-white/10 transition-colors"
                >
                  X
                </button>
              </div>
            </div>
          ) : ticket.emailCiudadano ? (
            <p className="text-gov-cyan-400 text-xs md:text-sm font-mono mt-0.5 break-all">
              {ticket.emailCiudadano}
            </p>
          ) : (
            <p className="text-white/40 text-xs italic mt-0.5">
              Anónimo · Dec. 1166/2016
            </p>
          )}
        </div>
      </div>

      {/* 1. CABECERA DEL TICKET */}
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-xs font-mono font-bold text-gov-gray-400 dark:text-dark-muted px-2 py-1 bg-gov-gray-100 dark:bg-dark-border rounded">
              {ticket.idTicket}
            </span>
            <StatusBadge estado={ticket.estado} />
            <UrgencyBadge nivelUrgencia={ticket.nivelUrgencia} diasRestantes={ticket.diasRestantes} />
          </div>

          {ticket.estado === 'Pendiente' && onCambiarEstado && (
            <button
              onClick={() => onCambiarEstado('En_Revision')}
              disabled={isSubmitting}
              className="flex items-center gap-2 px-4 py-2 bg-gov-blue-100 hover:bg-gov-blue-200 text-gov-blue-700 dark:bg-dark-accent/10 dark:hover:bg-dark-accent/20 dark:text-dark-cyan text-xs font-black uppercase tracking-widest rounded-lg transition-all border border-gov-blue-200 dark:border-dark-cyan/30"
            >
              {isSubmitting ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <ShieldCheck size={14} />
              )}
              Comenzar Revisión
            </button>
          )}
        </div>
        
        <div>
          <h1 className="text-2xl font-bold text-gov-gray-900 dark:text-dark-text tracking-tight">
            {ticket.nombreCiudadano}
          </h1>
          <div className="flex items-center gap-3 mt-1">
            <span className="text-sm font-semibold text-gov-blue-700 dark:text-dark-cyan bg-gov-blue-100/50 dark:bg-dark-accent/20 px-2 py-0.5 rounded">
              {ticket.tipoSolicitud}
            </span>
            <CanalEntry canal={ticket.canalOrigen} />
          </div>
        </div>
      </div>

      {/* 2. PANEL DE METADATOS */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {[
          { label: 'Fecha de Creación', value: formatearFecha(ticket.fechaCreacion), icon: Calendar },
          { 
            label: 'Fecha Límite Legal', 
            value: formatearFecha(ticket.fechaLimite), 
            icon: Calendar,
            className: isCritical ? 'text-sem-red font-bold' : ''
          },
          { 
            label: 'Días Restantes', 
            value: `${ticket.diasRestantes} días hábiles`, 
            icon: Clock,
            className: cn("font-bold", urgencyColor)
          },
          { 
            label: 'Dependencia Responsable', 
            value: (
              <div className="flex items-center gap-2">
                <span 
                  className="w-2.5 h-2.5 rounded-full shrink-0" 
                  style={{ backgroundColor: secretaria?.colorIdentificador || '#ccc' }}
                />
                {secretaria?.nombre || 'Secretaría no asignada'}
              </div>
            ), 
            icon: ShieldCheck 
          },
        ].map((item, idx) => (
          <div key={idx} className="bg-white dark:bg-dark-surface border border-gov-gray-100 dark:border-dark-border p-4 rounded-xl shadow-sm space-y-1">
            <div className="flex items-center gap-2 text-[10px] font-bold text-gov-gray-400 dark:text-dark-muted uppercase tracking-wider">
              <item.icon size={12} />
              {item.label}
            </div>
            <div className={cn("text-sm text-gov-gray-900 dark:text-dark-text font-medium", item.className)}>
              {item.value}
            </div>
          </div>
        ))}
      </div>

      {/* 3. SECCIÓN "MENSAJE ORIGINAL" */}
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-bold text-gov-gray-900 dark:text-dark-text uppercase tracking-wide">
          <MessageSquare size={18} className="text-gov-blue-700 dark:text-dark-cyan" />
          Mensaje Original del Ciudadano
        </div>
        <div className="relative bg-gov-gray-50 dark:bg-dark-bg border border-gov-gray-200 dark:border-dark-border rounded-xl p-6">
          <div className="absolute top-0 right-6 -translate-y-1/2 bg-white dark:bg-dark-surface px-3 py-0.5 border border-gov-gray-200 dark:border-dark-border rounded-full text-[10px] font-bold text-gov-gray-500 dark:text-dark-muted uppercase">
            {ticket.canalOrigen}
          </div>
          <p className="text-sm text-gov-gray-700 dark:text-dark-muted leading-relaxed whitespace-pre-wrap font-medium italic italic-none">
            &quot;{ticket.contenidoRaw}&quot;
          </p>
        </div>
      </div>

      {/* 4. SECCIÓN "ANÁLISIS DE IA" */}
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-bold text-gov-gray-900 dark:text-dark-text uppercase tracking-wide">
          <Sparkles size={18} className="text-gov-cyan-400" />
          Análisis de IA GovTech
        </div>
        
        {resumenCargando ? (
          <div className="flex items-center gap-3 p-4 bg-gov-cyan-50/40 dark:bg-dark-accent/10 border border-gov-cyan-200/60 dark:border-dark-accent/20 rounded-xl text-gov-gray-700 dark:text-dark-muted">
            <Loader2 size={18} className="text-gov-cyan-500 dark:text-dark-cyan animate-spin shrink-0" />
            <span className="text-sm font-medium">
              Generando resumen ejecutivo con el gateway (PQRSD-Assistant)…
            </span>
          </div>
        ) : ticket.resumenIa ? (
          <div className="bg-gov-cyan-100/20 dark:bg-dark-accent/10 border-l-4 border-gov-cyan-400 p-6 rounded-r-xl space-y-2">
            <div className="text-[10px] font-black text-gov-cyan-500 dark:text-dark-cyan uppercase mb-2">
              Resumen ejecutivo generado automáticamente
            </div>
            <p className="text-sm text-gov-gray-800 dark:text-dark-text leading-relaxed font-semibold whitespace-pre-wrap">
              {ticket.resumenIa}
            </p>
            {resumenError ? (
              <div className="flex items-start gap-2 pt-2 text-[11px] text-amber-800 bg-amber-50/80 border border-amber-200/60 rounded-lg px-3 py-2">
                <AlertCircle size={14} className="shrink-0 mt-0.5" />
                <span>
                  No se pudo generar el resumen en vivo ({resumenError}). Si ves texto arriba, es el
                  borrador local de la sesión.
                </span>
              </div>
            ) : null}
          </div>
        ) : resumenError ? (
          <div className="flex items-start gap-3 p-4 bg-sem-red-bg border border-sem-red/20 rounded-xl text-sem-red text-sm">
            <AlertCircle size={18} className="shrink-0" />
            <span>No se pudo obtener el resumen ejecutivo: {resumenError}</span>
          </div>
        ) : (
          <div className="flex items-center gap-3 p-4 bg-gov-gray-50 border border-dashed border-gov-gray-300 rounded-xl text-gov-gray-500 italic">
            <Clock size={16} />
            <span className="text-sm font-medium">La IA aún no ha terminado de procesar este ticket...</span>
          </div>
        )}
      </div>

      {/* 5. HISTORIAL DE COMUNICACIONES */}
      <EmailStatusTracker
        idTicket={ticket.idTicket}
      />
    </div>
  );
}
