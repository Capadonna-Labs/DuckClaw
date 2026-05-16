'use client';

import { useEffect, useRef } from 'react';
import { Send, ArrowLeft, AlertTriangle } from 'lucide-react';
import RadicadoBadge from '@/components/ticket/RadicadoBadge';

export interface ConfirmModalResumen {
  destinatario:     string;
  numeroRadicado:   string;
  nombreCiudadano:  string;
  longitudRespuesta: number;
  secretariaNombre: string;
  nombreFuncionario: string;
  cargoFuncionario:  string;
}

interface ConfirmModalProps {
  isOpen:     boolean;
  onConfirm:  () => void;
  onCancel:   () => void;
  isLoading?: boolean;    // deshabilita botón confirmar mientras se envía
  resumen:    ConfirmModalResumen;
}

export default function ConfirmModal({
  isOpen, onConfirm, onCancel, isLoading = false, resumen
}: ConfirmModalProps) {
  const confirmBtnRef = useRef<HTMLButtonElement>(null);

  // Focus en el botón cancelar al abrir (por seguridad, no en el de confirmar)
  useEffect(() => {
    if (isOpen) {
      // Pequeño delay para que el DOM renderice
      const t = setTimeout(() => {
        // No hacer foco automático en confirm para evitar envíos accidentales
      }, 50);
      return () => clearTimeout(t);
    }
  }, [isOpen]);

  // ESC deliberadamente NO cierra el modal (acción irreversible)
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault(); // bloquear cierre por ESC
        e.stopPropagation();
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isOpen]);

  if (!isOpen) return null;

  const filas: { label: string; value: React.ReactNode }[] = [
    {
      label: 'Destinatario',
      value: <span className="font-mono text-[#0057B8] dark:text-dark-cyan text-sm">{resumen.destinatario}</span>
    },
    { label: 'Ciudadano',    value: resumen.nombreCiudadano },
    {
      label: 'Radicado',
      value: <RadicadoBadge numeroRadicado={resumen.numeroRadicado} variant="short" />
    },
    { label: 'Dependencia',  value: resumen.secretariaNombre },
    {
      label: 'Funcionario',
      value: <span className="font-semibold">{resumen.nombreFuncionario} · {resumen.cargoFuncionario}</span>
    },
    { label: 'Longitud',     value: `${resumen.longitudRespuesta} caracteres` },
  ];

  return (
    <>
      {/* Backdrop — click NO cierra el modal */}
      <div className="fixed inset-0 bg-[#1A2332]/70 backdrop-blur-sm z-[200]"
           aria-hidden="true" />

      {/* Modal */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-modal-title"
        className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2
          w-full max-w-lg z-[201] bg-white dark:bg-dark-surface
          rounded-2xl shadow-2xl overflow-hidden"
      >
        {/* Cabecera */}
        <div className="bg-[#001E4E] p-5 flex items-start gap-3">
          <div className="w-10 h-10 bg-[#003DA5] rounded-xl flex items-center
            justify-center flex-shrink-0">
            <Send size={18} className="text-[#00A3E0]" />
          </div>
          <div>
            <h2
              id="confirm-modal-title"
              className="text-white font-bold text-base"
            >
              Confirmar Envío de Respuesta Oficial
            </h2>
            <p className="text-[#6B7A90] text-xs mt-0.5">
              Esta acción enviará un correo oficial al ciudadano y es irreversible.
            </p>
          </div>
        </div>

        {/* Cuerpo */}
        <div className="p-5 space-y-4">
          {/* Resumen del envío */}
          <div className="bg-[#F4F6F9] dark:bg-dark-bg border border-[#E8ECF2]
            dark:border-dark-border rounded-xl overflow-hidden">
            {filas.map((fila, i) => (
              <div
                key={fila.label}
                className={`flex items-center gap-3 px-4 py-2.5 text-sm
                  ${i < filas.length - 1
                    ? 'border-b border-[#E8ECF2] dark:border-dark-border'
                    : ''
                  }`}
              >
                <span className="text-[#6B7A90] dark:text-dark-muted
                  text-xs font-medium w-28 flex-shrink-0">
                  {fila.label}
                </span>
                <span className="text-[#1A2332] dark:text-dark-text">
                  {fila.value}
                </span>
              </div>
            ))}
          </div>

          {/* Aviso legal */}
          <div className="bg-[#FDF3D0] dark:bg-[#D4A017]/10
            border border-[#D4A017]/30 rounded-xl p-3
            flex items-start gap-2.5">
            <AlertTriangle size={15} className="text-[#D4A017] flex-shrink-0 mt-0.5" />
            <p className="text-xs text-[#3D4A5C] dark:text-dark-text leading-relaxed">
              Al confirmar, esta comunicación quedará registrada como respuesta oficial
              del <strong>Distrito de Medellín</strong> bajo su responsabilidad como
              funcionario público. Verifique el contenido antes de continuar.
            </p>
          </div>
        </div>

        {/* Acciones */}
        <div className="flex items-center justify-between p-4
          border-t border-[#E8ECF2] dark:border-dark-border
          bg-[#F4F6F9] dark:bg-dark-bg">
          <button
            onClick={onCancel}
            disabled={isLoading}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium
              text-[#3D4A5C] dark:text-dark-muted
              border border-[#6B7A90]/30 dark:border-dark-border
              rounded-lg hover:bg-white dark:hover:bg-dark-surface
              disabled:opacity-50 transition-colors"
          >
            <ArrowLeft size={14} />
            Revisar de nuevo
          </button>

          <button
            ref={confirmBtnRef}
            onClick={onConfirm}
            disabled={isLoading}
            className="flex items-center gap-2 px-5 py-2 text-sm font-bold
              bg-[#003DA5] hover:bg-[#001E4E] text-white rounded-lg
              disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white
                  rounded-full animate-spin" />
                Enviando...
              </>
            ) : (
              <>
                <Send size={14} />
                Sí, Enviar Respuesta Oficial
              </>
            )}
          </button>
        </div>
      </div>
    </>
  );
}
