'use client';

import { 
  FileEdit, 
  RotateCcw, 
  CheckCircle2, 
  AlertTriangle, 
  AlertCircle,
  Loader2,
  SendHorizontal
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { TicketConUrgencia, EmailSendResult } from '@/types';
import { IAAssistantPanel } from './';
import ConfirmModal from '@/components/shared/ConfirmModal';
import { useAuthStore } from '@/store/authStore';
interface ResponseEditorProps {
  ticket: TicketConUrgencia;
  respuestaActual: string;
  respuestaSugerida: string | null;
  isSubmitting: boolean;
  submitSuccess: boolean;
  hasUnsavedChanges: boolean;
  error: string | null;
  isConfirmModalOpen:  boolean;
  isSendingEmail:      boolean;
  emailSendResult:     EmailSendResult | null;
  emailError:          string | null;
  onRespuestaChange: (texto: string) => void;
  onReset: () => void;
  onOpenConfirmModal:  () => void;
  onCloseConfirmModal: () => void;
  onConfirmarEnvio:    () => void;
}

export default function ResponseEditor({
  ticket,
  respuestaActual,
  respuestaSugerida,
  isSubmitting,
  submitSuccess,
  hasUnsavedChanges,
  error,
  isConfirmModalOpen,
  isSendingEmail,
  emailSendResult,
  emailError,
  onRespuestaChange,
  onReset,
  onOpenConfirmModal,
  onCloseConfirmModal,
  onConfirmarEnvio
}: ResponseEditorProps) {
  const usuario = useAuthStore(s => s.usuario);
  const charCount = respuestaActual.length;
  const isTooShort = charCount < 50;
  const isEmpty = respuestaActual.trim().length === 0;

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isEmpty && !isTooShort && !isSubmitting) {
      onOpenConfirmModal();
    }
  };

  return (
    <div className="flex flex-col gap-6 bg-white dark:bg-dark-surface border border-gov-gray-100 dark:border-dark-border rounded-2xl shadow-sm p-6">
      {usuario && (
        <ConfirmModal
          isOpen={isConfirmModalOpen}
          onConfirm={onConfirmarEnvio}
          onCancel={onCloseConfirmModal}
          isLoading={isSendingEmail}
          resumen={{
            destinatario:      ticket.emailCiudadano ?? 'Sin email (solicitud anónima)',
            numeroRadicado:    ticket.numeroRadicado,
            nombreCiudadano:   ticket.nombreCiudadano,
            longitudRespuesta: respuestaActual.length,
            secretariaNombre:  usuario.secretariaNombre,
            nombreFuncionario: usuario.nombreCompleto,
            cargoFuncionario:  usuario.cargo,
          }}
        />
      )}
      {/* 1. CABECERA DEL PANEL */}
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-gov-gray-900 dark:text-dark-text font-bold">
            <FileEdit size={20} className="text-gov-blue-700 dark:text-dark-cyan" />
            <h2 className="text-lg">Módulo de Respuesta Oficial</h2>
          </div>
          <p className="text-sm text-gov-gray-500 dark:text-dark-muted">
            Valida y emite la respuesta formal al ciudadano
          </p>
        </div>
        
        {respuestaSugerida && (
          <div className="flex items-center gap-1.5 bg-gov-cyan-100 dark:bg-dark-accent/10 text-gov-cyan-500 dark:text-dark-cyan px-2.5 py-1 rounded-full text-[10px] font-black uppercase tracking-wider border border-gov-cyan-500/10 dark:border-dark-cyan/20">
            <div className="w-1.5 h-1.5 bg-gov-cyan-400 dark:bg-dark-cyan rounded-full animate-pulse" />
            Borrador IA disponible
          </div>
        )}
      </div>

      <div className="space-y-4">
        {/* 2. CONTADOR DE CARACTERES */}
        <div className="flex justify-end items-center gap-2 pr-1">
          {isEmpty ? (
             <span className="text-[10px] uppercase font-bold text-gov-gray-400 tracking-tighter">Campo obligatorio</span>
          ) : isTooShort ? (
            <div className="flex items-center gap-1.5 text-sem-red text-[11px] font-bold uppercase transition-all">
              <AlertCircle size={14} />
              {charCount} / 50 caracteres mínimos
            </div>
          ) : (
            <div className="flex items-center gap-1.5 text-sem-green text-[11px] font-bold uppercase transition-all">
              <CheckCircle2 size={14} />
              {charCount} caracteres registrados
            </div>
          )}
        </div>

        {/* 3. TEXTAREA PRINCIPAL */}
        <form onSubmit={handleFormSubmit} className="relative">
          <textarea
            className={cn(
              "w-full min-h-[320px] p-5 text-sm text-gov-gray-900 dark:text-dark-text border rounded-xl resize-y leading-relaxed transition-all shadow-inner bg-gov-gray-50/30 dark:bg-dark-bg",
              error ? "border-sem-red ring-1 ring-sem-red" : "border-gov-gray-300 dark:border-dark-border focus:ring-2 focus:ring-gov-blue-500 focus:border-transparent",
              isSubmitting && "opacity-50 cursor-not-allowed"
            )}
            placeholder="Escribe o valida la respuesta oficial aquí..."
            value={respuestaActual}
            onChange={(e) => onRespuestaChange(e.target.value)}
            disabled={isSubmitting}
            spellCheck="true"
          />
        </form>

        {/* ASISTENTE IA (Co-pilot) */}
        <IAAssistantPanel
          ticket={ticket}
          onRespuestaGenerada={(texto) => onRespuestaChange(texto)}
          iaHabilitada={process.env.NEXT_PUBLIC_IA_HABILITADA === 'true'}
        />

        {/* 4. AVISO INSTITUCIONAL */}
        <div className="bg-gov-gold-100/50 dark:bg-[#D4A017]/10 border border-gov-gold-500/20 dark:border-[#D4A017]/20 rounded-xl p-4 flex gap-3">
          <AlertTriangle size={20} className="text-gov-gold-500 shrink-0" />
          <div className="space-y-1">
            <p className="text-xs font-bold text-gov-gray-900 dark:text-dark-text uppercase tracking-tight">Recordatorio Institucional</p>
            <p className="text-[11px] text-gov-gray-700 dark:text-dark-muted leading-normal">
              Esta respuesta será registrada como comunicación oficial del Distrito de Medellín. 
              Asegúrate de cumplir con el lenguaje inclusivo y el protocolo de servicio al ciudadano.
            </p>
          </div>
        </div>
      </div>

      {/* 6. FEEDBACK DE ÉXITO O ERROR */}
      {submitSuccess && (
        <div className={cn(
          "rounded-xl p-4 space-y-2 animate-in fade-in slide-in-from-top-2 duration-300",
          ticket.emailCiudadano
            ? 'bg-sem-green-bg dark:bg-sem-green/10 border border-sem-green/30 dark:border-sem-green/20'
            : 'bg-gov-blue-50 dark:bg-gov-blue-900/20 border border-gov-blue-200 dark:border-gov-blue-800'
        )}>
          <div className="flex items-center gap-2">
            <CheckCircle2 size={16} className={ticket.emailCiudadano ? 'text-sem-green' : 'text-gov-blue-600 dark:text-gov-blue-400'} />
            <span className={cn(
              "text-sm font-bold",
              ticket.emailCiudadano ? 'text-sem-green' : 'text-gov-blue-700 dark:text-gov-blue-400'
            )}>
              {ticket.emailCiudadano ? 'Respuesta enviada exitosamente' : 'Ticket actualizado'}
            </span>
          </div>

          {ticket.emailCiudadano && emailSendResult && (
            <p className="text-xs text-sem-green/80 dark:text-sem-green/70 pl-6 font-medium leading-relaxed">
              {emailSendResult.simulado
                ? '✉️ Email simulado (SMTP_MODE=mock). Revisa la terminal de Next.js para ver el contenido.'
                : `✉️ Correo enviado a ${ticket.emailCiudadano}. ID: ${emailSendResult.messageId}`
              }
            </p>
          )}

          {emailSendResult?.simulado && (
            <p className="text-xs text-gov-gold-600 dark:text-gov-gold-400 pl-6 font-bold uppercase tracking-wider">
              ⚙️ Cambia SMTP_MODE=live en .env.local para envíos reales con Gmail.
            </p>
          )}

          {!ticket.emailCiudadano && (
            <p className="text-xs text-gov-blue-600/80 dark:text-gov-blue-400/80 pl-6 font-medium">
              Solicitud anónima — sin notificación por correo (Decreto 1166/2016).
            </p>
          )}
        </div>
      )}

      {(error || emailError) && !submitSuccess && (
        <div className="bg-sem-red-bg border border-sem-red/30 rounded-xl p-4 flex items-center gap-3 animate-in fade-in slide-in-from-top-2 duration-300">
          <AlertCircle className="text-sem-red" size={20} />
          <p className="text-sm font-bold text-sem-red">
            {error || emailError}
          </p>
        </div>
      )}

      {/* 5. BARRA DE ACCIONES */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between border-t border-gov-gray-100 dark:border-dark-border pt-6 gap-4">
        <div className="flex justify-start">
          {respuestaSugerida !== null && hasUnsavedChanges && !submitSuccess && (
            <button
              onClick={onReset}
              className="w-full sm:w-auto flex items-center justify-center gap-2 px-4 py-2 text-xs font-bold text-gov-blue-700 hover:bg-gov-blue-50 rounded-lg transition-all border border-gov-blue-200 dark:border-dark-cyan/20 dark:text-dark-cyan"
              title="Restaurar a la sugerencia original de la IA"
            >
              <RotateCcw size={14} />
              Restaurar Borrador IA
            </button>
          )}
        </div>

        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-4 sm:gap-5">
          {hasUnsavedChanges && !submitSuccess && !isSubmitting && (
            <span className="text-[10px] sm:text-[11px] font-bold text-sem-yellow uppercase animate-pulse text-center">
              Cambios sin guardar
            </span>
          )}
          
          <button
            onClick={onOpenConfirmModal}
            disabled={isSubmitting || isTooShort || isEmpty}
            className={cn(
              "flex items-center justify-center gap-3 px-8 py-3.5 sm:py-3 rounded-xl font-bold text-sm transition-all shadow-lg",
              (isSubmitting || isTooShort || isEmpty)
                ? "bg-gov-gray-300 text-gov-gray-500 cursor-not-allowed shadow-none"
                : "bg-gov-blue-700 hover:bg-gov-blue-900 text-white hover:scale-[1.02] active:scale-[0.98] shadow-gov-blue-900/20"
            )}
          >
            {isSubmitting ? (
              <>
                <Loader2 size={18} className="animate-spin" />
                Enviando...
              </>
            ) : (
              <>
                <SendHorizontal size={18} />
                Enviar Respuesta Oficial
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
