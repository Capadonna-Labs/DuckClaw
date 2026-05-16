'use client';

import { useState, useRef, useEffect } from 'react';
import { Bell, Clock, AlertTriangle, ChevronRight } from 'lucide-react';
import { useNotifications } from '@/hooks/useNotifications';
import { useRouter } from 'next/navigation';
import { cn } from '@/lib/utils';

export default function NotificationBell() {
  const [isOpen, setIsOpen] = useState(false);
  const { 
    notificaciones, 
    totalCriticas, 
    hayVencidos, 
    vistas, 
    marcarComoVista, 
    marcarTodasVistas 
  } = useNotifications();
  
  const router = useRouter();
  const dropdownRef = useRef<HTMLDivElement>(null);

  const noVistasCount = notificaciones.filter(n => !vistas.has(n.idTicket)).length;

  // Cierra el dropdown al hacer clic fuera
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleNotificationClick = (idTicket: string) => {
    marcarComoVista(idTicket);
    setIsOpen(false);
    router.push(`/ticket/${idTicket}`);
  };

  return (
    <div className="relative" ref={dropdownRef}>
      {/* TRIGGER BUTTON */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          "relative p-2 rounded-lg transition-all",
          isOpen ? "bg-gov-gray-100" : "hover:bg-gov-gray-100"
        )}
        aria-label="Abrir centro de notificaciones"
      >
        <Bell 
          size={20} 
          className={cn(
            "transition-colors",
            notificaciones.length === 0 ? "text-gov-gray-400" : 
            hayVencidos || totalCriticas > 0 ? "text-sem-red animate-bell-ring" : "text-sem-yellow"
          )}
        />
        
        {noVistasCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] bg-sem-red text-white text-[10px] font-bold rounded-full flex items-center justify-center px-1 border-2 border-white">
            {noVistasCount}
          </span>
        )}
      </button>

      {/* DROPDOWN PANEL */}
      {isOpen && (
        <div className="absolute right-0 top-12 w-80 bg-white rounded-xl shadow-[0_20px_50px_rgba(0,0,0,0.15)] border border-gov-gray-100 overflow-hidden z-50 animate-in fade-in slide-in-from-top-2 duration-200">
          
          {/* CABECERA */}
          <div className="bg-gov-gray-50/50 p-4 border-b border-gov-gray-100">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-gov-gray-900">Alertas de Urgencia</h3>
                <span className="bg-gov-blue-100 text-gov-blue-700 text-[10px] font-black px-1.5 py-0.5 rounded-full">
                  {notificaciones.length}
                </span>
              </div>
              {noVistasCount > 0 && (
                <button 
                  onClick={marcarTodasVistas}
                  className="text-[10px] font-bold text-gov-blue-600 hover:text-gov-blue-800 transition-colors uppercase tracking-tighter"
                >
                  Marcar todas vistas
                </button>
              )}
            </div>
          </div>

          {/* LISTA */}
          <div className="max-h-96 overflow-y-auto divide-y divide-gov-gray-50">
            {notificaciones.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 px-6 text-center">
                <div className="w-12 h-12 bg-gov-gray-50 rounded-full flex items-center justify-center mb-3">
                  <Bell size={24} className="text-gov-gray-200" />
                </div>
                <p className="text-sm font-bold text-gov-gray-900">Sin alertas activas</p>
                <p className="text-xs text-gov-gray-400 mt-1">Todos los tickets están dentro del plazo legal.</p>
              </div>
            ) : (
              notificaciones.map((n) => {
                const isVista = vistas.has(n.idTicket);
                return (
                  <div
                    key={n.idTicket}
                    onClick={() => handleNotificationClick(n.idTicket)}
                    className={cn(
                      "flex items-start gap-3 p-4 cursor-pointer transition-colors group",
                      isVista ? "opacity-50 grayscale-[0.5]" : "hover:bg-gov-gray-50"
                    )}
                  >
                    <div className={cn(
                      "w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm",
                      n.diasRestantes < 0 ? "bg-sem-red-bg text-sem-red" : 
                      n.diasRestantes <= 3 ? "bg-sem-red-bg/50 text-sem-red" : "bg-sem-yellow-bg text-sem-yellow"
                    )}>
                      {n.diasRestantes < 0 ? <AlertTriangle size={18} /> : <Clock size={18} />}
                    </div>

                    <div className="flex-1 space-y-1">
                      <div className="flex justify-between items-start">
                        <span className="text-[11px] font-bold text-gov-gray-900 leading-tight">
                          {n.nombreCiudadano}
                        </span>
                        {!isVista && (
                          <div className="w-1.5 h-1.5 bg-gov-blue-600 rounded-full mt-1 shrink-0" />
                        )}
                      </div>
                      <p className={cn(
                        "text-[10px] font-bold uppercase tracking-tight",
                        n.diasRestantes < 0 ? "text-sem-red" : "text-gov-gray-600"
                      )}>
                        {n.mensaje}
                      </p>
                      <div className="flex items-center gap-2 mt-1">
                         <span className="text-[9px] bg-gov-gray-100 text-gov-gray-500 font-black px-1.5 py-0.5 rounded uppercase">
                            {n.tipoSolicitud}
                         </span>
                         <span className="text-[9px] font-mono text-gov-gray-400">{n.idTicket}</span>
                      </div>
                    </div>

                    <ChevronRight size={14} className="text-gov-gray-300 mt-2 group-hover:text-gov-gray-500" />
                  </div>
                );
              })
            )}
          </div>

          {/* PIE */}
          {notificaciones.length > 0 && (
            <div className="p-3 bg-gov-gray-50/50 text-center border-t border-gov-gray-100">
              <button
                onClick={() => { setIsOpen(false); router.push('/dashboard'); }}
                className="text-xs font-bold text-gov-blue-700 hover:text-gov-blue-900 transition-colors uppercase tracking-tight"
              >
                Ver todos en el dashboard
              </button>
            </div>
          )}
        </div>
      )}

      {/* ANIMACIONES CSS */}
      <style jsx global>{`
        @keyframes bell-ring {
          0% { transform: rotate(0); }
          5% { transform: rotate(15deg); }
          10% { transform: rotate(-15deg); }
          15% { transform: rotate(15deg); }
          20% { transform: rotate(-15deg); }
          25% { transform: rotate(15deg); }
          30% { transform: rotate(0); }
          100% { transform: rotate(0); }
        }
        .animate-bell-ring {
          animation: bell-ring 2s ease-in-out infinite;
          transform-origin: top center;
        }
      `}</style>
    </div>
  );
}
