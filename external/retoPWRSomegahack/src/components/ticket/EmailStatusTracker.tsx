'use client';

import { useState } from 'react';
import { Mail, CheckCircle2, AlertCircle, Clock, Zap, MailX } from 'lucide-react';
import { getRegistrosEmailByTicket } from '@/services/mockData';
import { useEmailSender } from '@/hooks/useEmailSender';
import type { RegistroEmail } from '@/types';
import { formatearFechaRelativa } from '@/lib/utils';

interface EmailStatusTrackerProps {
  idTicket:       string;
}

export default function EmailStatusTracker({ idTicket }: EmailStatusTrackerProps) {
  const { historialSesion } = useEmailSender();

  // Combina: registros mock persistidos + registros nuevos de la sesión actual
  const [registrosMock] = useState<RegistroEmail[]>(() =>
    getRegistrosEmailByTicket(idTicket)
  );

  // Los registros de sesión relacionados con este ticket
  const registrosSesion = historialSesion.filter(r => r.idTicket === idTicket);

  // Todos los registros, sin duplicados, ordenados por fecha desc
  const todosLosRegistros = [
    ...registrosSesion,
    ...registrosMock.filter(m => !registrosSesion.some(s => s.idRegistro === m.idRegistro)),
  ].sort((a, b) => new Date(b.fechaEnvio).getTime() - new Date(a.fechaEnvio).getTime());

  const CONFIG_ESTADO = {
    enviado:  { icon: CheckCircle2, color: 'text-[#00875A]',   bg: 'bg-[#ECFDF5] dark:bg-sem-green/10',  label: 'Enviado'  },
    simulado: { icon: Zap,          color: 'text-[#D4A017]', bg: 'bg-[#FDF3D0] dark:bg-[#D4A017]/10',  label: 'Simulado' },
    fallido:  { icon: AlertCircle,  color: 'text-[#DC2626]',      bg: 'bg-[#FEF2F2] dark:bg-sem-red/10',    label: 'Fallido'  },
    pendiente:{ icon: Clock,        color: 'text-[#6B7A90]',        bg: 'bg-[#F4F6F9] dark:bg-dark-border',  label: 'Pendiente'},
  } as const;

  const LABEL_TIPO: Record<string, string> = {
    confirmacion_radicado: 'Confirmación de Radicado',
    respuesta_oficial:     'Respuesta Oficial al Ciudadano',
  };

  return (
    <div className="mt-4 pt-4 border-t border-[#E8ECF2] dark:border-dark-border">
      {/* Cabecera */}
      <div className="flex items-center gap-2 mb-3">
        <Mail size={14} className="text-[#6B7A90]" />
        <h3 className="text-xs font-bold text-[#3D4A5C] dark:text-dark-muted uppercase tracking-wide">
          Historial de Comunicaciones
        </h3>
        {todosLosRegistros.length > 0 && (
          <span className="text-[10px] bg-[#0057B8]/10 text-[#0057B8]
            dark:bg-dark-accent/20 dark:text-dark-cyan
            px-1.5 py-0.5 rounded-full font-bold">
            {todosLosRegistros.length}
          </span>
        )}
      </div>

      {/* Lista de registros */}
      {todosLosRegistros.length === 0 ? (
        <div className="flex items-center gap-2 text-[#6B7A90] py-2">
          <MailX size={16} />
          <span className="text-xs">Sin comunicaciones registradas para este ticket.</span>
        </div>
      ) : (
        <div className="space-y-2">
          {todosLosRegistros.map((reg) => {
            const cfg = CONFIG_ESTADO[reg.estado] ?? CONFIG_ESTADO.pendiente;
            const Icon = cfg.icon;
            return (
              <div
                key={reg.idRegistro}
                className="flex items-start gap-3 p-2.5 rounded-lg
                  bg-[#F4F6F9] dark:bg-dark-surface
                  border border-[#E8ECF2] dark:border-dark-border"
              >
                {/* Ícono de estado */}
                <div className={`w-7 h-7 rounded-full flex items-center justify-center
                  flex-shrink-0 ${cfg.bg}`}>
                  <Icon size={14} className={cfg.color} />
                </div>

                {/* Contenido */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-semibold text-[#1A2332] dark:text-dark-text">
                      {LABEL_TIPO[reg.tipoEmail] ?? reg.tipoEmail}
                    </span>
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full
                      ${cfg.bg} ${cfg.color}`}>
                      {cfg.label}
                    </span>
                    {reg.estado === 'simulado' && (
                      <span className="text-[10px] bg-[#FDF3D0] dark:bg-[#D4A017]/10 text-[#D4A017]
                        px-1.5 py-0.5 rounded-full font-bold border border-[#D4A017]/20">
                        DEMO
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-[#3D4A5C] dark:text-dark-muted mt-0.5 truncate">
                    Para: <span className="font-mono">{reg.destinatario}</span>
                  </p>
                  <p className="text-[10px] text-[#6B7A90] mt-0.5">
                    {formatearFechaRelativa(reg.fechaEnvio)}
                    {reg.messageId && (
                      <span className="font-mono ml-2 opacity-60 hidden sm:inline">
                        {reg.messageId.substring(0, 30)}...
                      </span>
                    )}
                  </p>
                  {reg.errorMensaje && (
                    <p className="text-[11px] text-[#DC2626] mt-1 bg-[#FEF2F2] dark:bg-sem-red/10
                      px-2 py-1 rounded">
                      ⚠ {reg.errorMensaje}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
