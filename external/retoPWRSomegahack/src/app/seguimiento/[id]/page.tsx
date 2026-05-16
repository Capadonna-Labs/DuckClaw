'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { 
  Building2, Clock, CheckCircle2, Search as SearchIcon, 
  FileText, Loader2, AlertCircle, ChevronRight 
} from 'lucide-react';

interface PublicTicketData {
  idTicket: string;
  numeroRadicado: string;
  tipoSolicitud: string;
  asunto: string;
  estado: string;
  nombreCiudadano: string;
  fechaCreacion: string;
  fechaLimite: string;
  fechaActualizacion: string;
}

const ESTADOS_ORDEN = ['Pendiente', 'En_Revision', 'Resuelto'];
const ESTADOS_LABEL: Record<string, string> = {
  Pendiente: 'Recibido',
  En_Revision: 'En Revisión',
  Resuelto: 'Resuelto',
};
const ESTADOS_ICON: Record<string, typeof Clock> = {
  Pendiente: FileText,
  En_Revision: SearchIcon,
  Resuelto: CheckCircle2,
};

function formatDate(iso: string) {
  try {
    return new Date(iso).toLocaleDateString('es-CO', {
      day: '2-digit',
      month: 'long',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export default function SeguimientoPage() {
  const params = useParams();
  const idTicket = params.id as string;

  const [data, setData] = useState<PublicTicketData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchPublicTicket() {
      try {
        const res = await fetch(`/api/tickets/${idTicket}/public`);
        const json = await res.json();

        if (!res.ok || json.error) {
          setError(json.error || 'No se encontró la solicitud');
          return;
        }
        setData(json.data);
      } catch {
        setError('Error de conexión. Intente nuevamente.');
      } finally {
        setLoading(false);
      }
    }

    if (idTicket) fetchPublicTicket();
  }, [idTicket]);

  const activeStepIndex = data ? ESTADOS_ORDEN.indexOf(data.estado) : -1;
  const progress = data 
    ? Math.round(((activeStepIndex + 1) / ESTADOS_ORDEN.length) * 100) 
    : 0;

  return (
    <div 
      className="min-h-screen flex flex-col"
      style={{ background: 'linear-gradient(180deg, #001E4E 0%, #003DA5 30%, #F4F6F9 30%)' }}
    >
      {/* Header */}
      <header className="px-4 sm:px-8 pt-6 pb-16 text-center">
        <div className="flex items-center justify-center gap-3 mb-2">
          <div className="w-10 h-10 bg-white/10 rounded-lg flex items-center justify-center">
            <Building2 size={22} className="text-white" />
          </div>
          <div className="text-left">
            <h1 className="text-white font-bold text-sm sm:text-base leading-tight">Alcaldía de Medellín</h1>
            <p className="text-cyan-300 text-[9px] font-bold uppercase tracking-widest">
              Portal de Seguimiento PQRSD
            </p>
          </div>
        </div>
      </header>

      {/* Main Card */}
      <main className="flex-1 px-4 sm:px-8 -mt-10">
        <div className="max-w-2xl mx-auto">
          {loading ? (
            <div className="bg-white rounded-2xl shadow-xl p-12 text-center space-y-4">
              <Loader2 size={40} className="animate-spin text-blue-600 mx-auto" />
              <p className="text-sm text-gray-500 font-medium">Consultando su solicitud...</p>
            </div>
          ) : error ? (
            <div className="bg-white rounded-2xl shadow-xl p-12 text-center space-y-4">
              <AlertCircle size={48} className="text-red-400 mx-auto" />
              <h2 className="text-lg font-bold text-gray-900">Solicitud no encontrada</h2>
              <p className="text-sm text-gray-500">{error}</p>
              <p className="text-xs text-gray-400">
                Verifique el enlace proporcionado en su correo de confirmación.
              </p>
            </div>
          ) : data ? (
            <div className="bg-white rounded-2xl shadow-xl overflow-hidden">
              {/* Radicado Banner */}
              <div 
                className="p-6 sm:p-8 text-center"
                style={{ background: 'linear-gradient(135deg, #001E4E, #003DA5)' }}
              >
                <p className="text-cyan-400 text-[9px] font-bold uppercase tracking-widest mb-2">
                  Número de Radicado Oficial
                </p>
                <p className="text-white font-mono text-xl sm:text-2xl font-bold tracking-wide">
                  {data.numeroRadicado}
                </p>
                <p className="text-white/50 text-xs mt-2">
                  {data.tipoSolicitud} · {data.asunto}
                </p>
              </div>

              {/* Stepper Visual */}
              <div className="p-6 sm:p-8 space-y-6">
                <div>
                  <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-3">
                    Estado de su solicitud
                  </p>

                  {/* Barra de progreso */}
                  <div className="w-full bg-gray-100 rounded-full h-2.5 mb-6 overflow-hidden">
                    <div 
                      className="h-full rounded-full transition-all duration-700 ease-out"
                      style={{ 
                        width: `${progress}%`,
                        background: progress === 100 
                          ? 'linear-gradient(90deg, #00875A, #34D399)' 
                          : 'linear-gradient(90deg, #003DA5, #0057B8)'
                      }}
                    />
                  </div>

                  {/* Steps */}
                  <div className="flex flex-col sm:flex-row gap-4 sm:gap-0 sm:justify-between">
                    {ESTADOS_ORDEN.map((estado, idx) => {
                      const isActive = idx <= activeStepIndex;
                      const isCurrent = idx === activeStepIndex;
                      const Icon = ESTADOS_ICON[estado];
                      
                      return (
                        <div 
                          key={estado} 
                          className={`flex items-center gap-3 sm:flex-col sm:items-center sm:gap-2 sm:flex-1 relative
                            ${isCurrent ? 'scale-105' : ''} transition-transform duration-300`}
                        >
                          <div className={`
                            w-10 h-10 rounded-full flex items-center justify-center shrink-0 transition-all duration-500
                            ${isActive 
                              ? (isCurrent 
                                ? 'bg-blue-600 text-white shadow-lg shadow-blue-300 ring-4 ring-blue-100' 
                                : 'bg-green-500 text-white') 
                              : 'bg-gray-100 text-gray-400'}
                          `}>
                            {isActive && idx < activeStepIndex ? (
                              <CheckCircle2 size={18} />
                            ) : (
                              <Icon size={18} />
                            )}
                          </div>
                          <div className="sm:text-center">
                            <p className={`text-xs font-bold ${isActive ? 'text-gray-900' : 'text-gray-400'}`}>
                              {ESTADOS_LABEL[estado]}
                            </p>
                            {isCurrent && (
                              <p className="text-[10px] text-blue-600 font-bold mt-0.5 animate-pulse">
                                Estado actual
                              </p>
                            )}
                          </div>

                          {/* Connector arrow (mobile) */}
                          {idx < ESTADOS_ORDEN.length - 1 && (
                            <ChevronRight size={14} className="text-gray-300 hidden sm:block absolute -right-2 top-3" />
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Metadata */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-4 border-t border-gray-100">
                  <div className="bg-gray-50 rounded-xl p-4 space-y-1">
                    <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
                      <Clock size={11} /> Fecha de radicación
                    </p>
                    <p className="text-sm font-semibold text-gray-900">
                      {formatDate(data.fechaCreacion)}
                    </p>
                  </div>
                  <div className="bg-gray-50 rounded-xl p-4 space-y-1">
                    <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
                      <Clock size={11} /> Fecha límite de respuesta
                    </p>
                    <p className="text-sm font-semibold text-gray-900">
                      {formatDate(data.fechaLimite)}
                    </p>
                  </div>
                  <div className="bg-gray-50 rounded-xl p-4 space-y-1 sm:col-span-2">
                    <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">
                      Última actualización
                    </p>
                    <p className="text-sm font-semibold text-gray-900">
                      {formatDate(data.fechaActualizacion)}
                    </p>
                  </div>
                </div>

                {/* Legal Notice */}
                <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 text-center">
                  <p className="text-[11px] text-blue-800 font-medium leading-relaxed">
                    De acuerdo con la <strong>Ley 1755 de 2015</strong>, la Alcaldía de Medellín 
                    responderá su solicitud dentro de los <strong>15 días hábiles</strong> siguientes 
                    a la fecha de radicación.
                  </p>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </main>

      {/* Footer */}
      <footer className="py-6 text-center">
        <p className="text-[10px] text-gray-400 font-medium">
          © {new Date().getFullYear()} Distrito Especial de Ciencia, Tecnología e Innovación de Medellín
        </p>
      </footer>
    </div>
  );
}
