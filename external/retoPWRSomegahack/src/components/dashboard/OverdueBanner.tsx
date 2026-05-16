'use client';

import { AlertOctagon } from 'lucide-react';
import { useNotifications } from '@/hooks/useNotifications';

/**
 * Banner de Alerta Crítica para tickets vencidos.
 * Aparece solo si hay tickets con días restantes negativos.
 */
export default function OverdueBanner() {
  const { notificaciones, hayVencidos } = useNotifications();
  
  // Contar cuántos tickets están realmente vencidos
  const vencidosCount = notificaciones.filter(n => n.diasRestantes < 0).length;

  if (!hayVencidos || vencidosCount === 0) {
    return null;
  }

  return (
    <div className="bg-sem-red text-white rounded-2xl p-5 flex items-center gap-5 mb-6 shadow-xl shadow-sem-red/20 animate-in slide-in-from-top duration-500 border-2 border-white/20">
      {/* Ícono animado */}
      <div className="bg-white/20 p-3 rounded-full animate-pulse shrink-0">
        <AlertOctagon size={28} className="text-white" strokeWidth={2.5} />
      </div>

      {/* Mensaje Legal */}
      <div className="flex-1">
        <h3 className="text-base font-black uppercase tracking-tight">
          ⚠️ ALERTA LEGAL: Tickets Fuera de Plazo
        </h3>
        <p className="text-xs font-medium opacity-90 mt-1 max-w-2xl leading-relaxed">
          Los siguientes trámites han superado el límite legal de 15 días hábiles establecido por la Ley 1755 de 2015. 
          La Alcaldía se encuentra en riesgo de sanción. Se requiere respuesta inmediata.
        </p>
      </div>

      {/* Contador de Impacto */}
      <div className="ml-auto text-right pr-2">
        <div className="text-4xl font-black leading-none">{vencidosCount}</div>
        <div className="text-[10px] font-bold uppercase tracking-widest mt-1 opacity-80">
          Trámites Vencidos
        </div>
      </div>
    </div>
  );
}
