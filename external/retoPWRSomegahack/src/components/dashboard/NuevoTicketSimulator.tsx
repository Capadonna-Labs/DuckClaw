'use client';

import { useState } from 'react';
import { useEmailSender } from '@/hooks/useEmailSender';
import { useAuthStore } from '@/store/authStore';
import { generarNumeroRadicado } from '@/lib/radicado';
import { addBusinessDays, formatISO } from 'date-fns';
import {
  Mail, Send, ChevronDown, ChevronUp,
  CheckCircle2, AlertCircle, Loader2
} from 'lucide-react';
import type { TipoSolicitud, ConfirmacionEmailPayload } from '@/types';
import { useTickets } from '@/hooks/useTickets';

type SimulationMode = 'form' | 'email';

export default function NuevoTicketSimulator() {
  const { dataMode } = useAuthStore();
  const [isExpanded, setIsExpanded] = useState(false);
  const [nombre, setNombre] = useState('');
  const [email, setEmail] = useState('');
  const [tipo, setTipo] = useState<TipoSolicitud>('Peticion');
  const [resultado, setResultado] = useState<{ 
    radicado: string; 
    simulado: boolean; 
    ia?: { templateSelected: string; score: number } 
  } | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [mode, setMode] = useState<SimulationMode>('form');
  const [asunto, setAsunto] = useState('');
  const [cuerpo, setCuerpo] = useState('');

  const { refetch } = useTickets();
  const { enviarConfirmacion, isSendingConfirmacion, error: apiError, limpiarError } = useEmailSender();

  if (dataMode === 'live') return null;

  async function handleSimular() {
    setLocalError(null);
    limpiarError();

    // 1. Validaciones básicas de UI
    if (!nombre.trim()) {
      setLocalError('El nombre es obligatorio');
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setLocalError('Formato de email inválido');
      return;
    }
    
    // 2. Obtener datos del usuario autenticado
    const usuario = useAuthStore.getState().usuario;
    if (!usuario) {
      setLocalError('No hay sesión activa para realizar la simulación');
      return;
    }
    
    // 3. Generar radicado y fecha límite
    const radicado = generarNumeroRadicado(usuario.idSecretaria);
    const fechaLimite = formatISO(addBusinessDays(new Date(), 15));
    
    // 4. Construir payload
    const payload: ConfirmacionEmailPayload = {
      idTicket: `TKT-DEMO-${Date.now()}`,
      numeroRadicado: radicado,
      emailCiudadano: email.trim(),
      nombreCiudadano: nombre.trim(),
      tipoSolicitud: tipo,
      secretariaNombre: usuario.secretariaNombre,
      fechaLimiteRespuesta: fechaLimite,
    };
    
    // 5. Enviar
    const result = await enviarConfirmacion(payload);
    
    // 6. Mostrar resultado
    if (result?.success) {
      setResultado({ radicado, simulado: result.simulado });
      setNombre('');
      setEmail('');
      refetch();
    }
  }

  async function handleSimularIngesta() {
    setLocalError(null);
    setResultado(null);

    if (!cuerpo.trim() || !email.trim()) {
      setLocalError('Email y Cuerpo son obligatorios para la ingesta');
      return;
    }

    try {
      const response = await fetch('/api/emails/incoming', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          remitente: email,
          nombre: nombre || 'Ciudadano Anónimo',
          asunto: asunto || 'PQRSD desde Correo',
          cuerpo: cuerpo
        })
      });

      const data = await response.json();
      if (data.success) {
        setResultado({ 
          radicado: data.numeroRadicado, 
          simulado: true,
          ia: data.ia
        });
        setAsunto('');
        setCuerpo('');
        refetch();
      } else {
        setLocalError(data.error || 'Error en la ingesta');
      }
    } catch {
      setLocalError('Error de red al simular ingesta');
    }
  }

  return (
    <div className="w-full">
      {/* CABECERA (Toggle) */}
      <div 
        onClick={() => setIsExpanded(!isExpanded)}
        className={`flex items-center justify-between p-3 rounded-xl cursor-pointer
          bg-gradient-to-r from-[#003DA5] via-[#0057B8] to-[#00A3E0]
          hover:opacity-90 transition-opacity select-none ${isExpanded ? 'rounded-b-none' : ''}`}
      >
        <div className="flex items-center gap-2">
          <Mail className="text-white w-4 h-4" />
          <span className="text-white font-semibold text-sm">Simular Ingreso de Ticket</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="bg-white/20 text-white text-[10px] font-bold px-2 py-0.5 rounded-full">DEMO</span>
          {isExpanded ? <ChevronUp className="text-white/70 w-4 h-4" /> : <ChevronDown className="text-white/70 w-4 h-4" />}
        </div>
      </div>

      {/* CUERPO */}
      {isExpanded && (
        <div className="border border-[#0057B8]/20 border-t-0 rounded-b-xl bg-[#F4F6F9]/50 dark:bg-dark-surface/80 p-4 space-y-3 shadow-inner">
          {/* Selectores de modo */}
          <div className="flex border-b border-[#E8ECF2] dark:border-dark-border mb-4">
            <button 
              onClick={() => { setMode('form'); setResultado(null); }}
              className={`px-4 py-2 text-xs font-bold transition-all ${mode === 'form' ? 'text-[#0057B8] border-b-2 border-[#0057B8]' : 'text-gov-gray-400'}`}
            >
              Registro Manual
            </button>
            <button 
              onClick={() => { setMode('email'); setResultado(null); }}
              className={`px-4 py-2 text-xs font-bold transition-all ${mode === 'email' ? 'text-[#0057B8] border-b-2 border-[#0057B8]' : 'text-gov-gray-400'}`}
            >
              Simular Email (IA)
            </button>
          </div>

          {/* Aviso informativo */}
          <div className="bg-[#FDF3D0] dark:bg-dark-accent/10 border border-[#D4A017]/30 dark:border-dark-cyan/20 rounded-lg p-2 flex gap-2 items-start">
            <span className="text-xs">⚙️</span>
            <p className="text-xs text-[#3D4A5C] dark:text-dark-muted">
              {mode === 'form' 
                ? 'Simula el registro de un ciudadano en ventanilla física.' 
                : 'Simula un correo real llegando al servidor. La IA lo clasificará automáticamente.'}
            </p>
          </div>

          {/* Formulario */}
          <div className="space-y-3">
            <div>
              <input 
                type="text"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                placeholder="Pedro Antonio Restrepo García"
                className="w-full text-sm border border-[#E8ECF2] dark:border-dark-border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#0057B8] bg-white dark:bg-dark-surface dark:text-white shadow-sm"
              />
            </div>
            <div>
              <input 
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="ciudadano@gmail.com"
                className="w-full text-sm border border-[#E8ECF2] dark:border-dark-border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#0057B8] bg-white dark:bg-dark-surface dark:text-white shadow-sm"
              />
            </div>
            {mode === 'email' && (
              <>
                <div>
                  <input 
                    type="text"
                    value={asunto}
                    onChange={(e) => setAsunto(e.target.value)}
                    placeholder="Asunto: Hueco peligroso en mi calle"
                    className="w-full text-sm border border-[#E8ECF2] dark:border-dark-border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#0057B8] bg-white dark:bg-dark-surface dark:text-white shadow-sm"
                  />
                </div>
                <div>
                  <textarea 
                    value={cuerpo}
                    onChange={(e) => setCuerpo(e.target.value)}
                    placeholder="Escribe el mensaje que enviaría el ciudadano..."
                    rows={3}
                    className="w-full text-sm border border-[#E8ECF2] dark:border-dark-border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#0057B8] bg-white dark:bg-dark-surface dark:text-white shadow-sm resize-none"
                  />
                </div>
              </>
            )}
            
            {mode === 'form' && (
              <div>
                <select 
                  value={tipo}
                  onChange={(e) => setTipo(e.target.value as TipoSolicitud)}
                  className="w-full text-sm border border-[#E8ECF2] dark:border-dark-border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#0057B8] bg-white dark:bg-dark-surface dark:text-white shadow-sm"
                >
                  <option value="Peticion" className="dark:bg-dark-surface">Petición</option>
                  <option value="Queja" className="dark:bg-dark-surface">Queja</option>
                  <option value="Reclamo" className="dark:bg-dark-surface">Reclamo</option>
                  <option value="Sugerencia" className="dark:bg-dark-surface">Sugerencia</option>
                  <option value="Denuncia" className="dark:bg-dark-surface">Denuncia</option>
                </select>
              </div>
            )}

            {/* Resultado o Errores */}
            {(localError || apiError) && (
              <div className="bg-[#FEF2F2] dark:bg-red-900/10 border border-[#DC2626]/30 dark:border-red-900/20 rounded-lg p-3 flex items-center gap-2">
                <AlertCircle className="text-[#DC2626] dark:text-sem-red w-4 h-4" />
                <p className="text-xs text-[#DC2626] dark:text-sem-red font-medium">{localError || apiError}</p>
              </div>
            )}

            {resultado && (
              <div className="bg-[#ECFDF5] dark:bg-green-900/10 border border-[#00875A]/30 dark:border-green-900/20 rounded-xl p-3 space-y-2 animate-in fade-in zoom-in duration-300">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="text-[#00875A] dark:text-sem-green w-5 h-5" />
                  <span className="text-sm font-semibold text-[#00875A] dark:text-sem-green">
                    {mode === 'email' ? 'Email Procesado por IA' : 'Ticket registrado exitosamente'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <div className="font-mono bg-[#001E4E] text-[#00A3E0] px-3 py-1 rounded-lg text-xs border border-white/10">
                    {resultado.radicado}
                  </div>
                  {resultado.ia && (
                    <div className="text-[10px] font-bold text-gov-cyan-500 uppercase">
                      Clasificado como: {resultado.ia.templateSelected}
                    </div>
                  )}
                </div>
                <p className="text-[10px] text-[#00875A] dark:text-sem-green/80">
                  {mode === 'email' 
                    ? 'Se ha generado un borrador de respuesta y enviado el correo de radicado.' 
                    : 'Se ha enviado una notificación de radicado a la bandeja del ciudadano.'}
                </p>
              </div>
            )}

            {/* Botón */}
            <button
              onClick={mode === 'form' ? handleSimular : handleSimularIngesta}
              disabled={isSendingConfirmacion || !nombre.trim() || !email.trim()}
              className={`w-full bg-[#003DA5] hover:bg-[#001E4E] text-white text-sm font-semibold py-2.5 rounded-lg flex items-center justify-center gap-2 transition-all shadow-md active:scale-95 disabled:opacity-50 disabled:pointer-events-none`}
            >
              {isSendingConfirmacion ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Procesando...</span>
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  <span>{mode === 'form' ? 'Registrar y Enviar Confirmación' : 'Simular Ingesta y Clasificación IA'}</span>
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
