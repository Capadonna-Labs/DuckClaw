import { useState, useEffect, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useIdSecretariaActivo, useAuthStore, useDataMode } from '@/store/authStore';
import { getTicketById, actualizarRespuesta } from '@/services/ticketService';
import { enriquecerTicketConUrgencia } from '@/lib/urgency';
import { TicketConUrgencia, RespuestaEmailPayload, EmailSendResult, TicketEstado } from '@/types';
import { SECRETARIAS_MOCK } from '@/services/mockData';
import { useEmailSender } from './useEmailSender';
import { format } from 'date-fns';
import { es } from 'date-fns/locale';

interface UseTicketDetailReturn {
  ticket: TicketConUrgencia | null;
  isLoading: boolean;
  error: string | null;
  respuestaActual: string;
  isSubmitting: boolean;
  submitSuccess: boolean;
  hasUnsavedChanges: boolean;
  resumenCargando: boolean;
  resumenError: string | null;

  isConfirmModalOpen: boolean;
  isSendingEmail:     boolean;
  emailSendResult:    EmailSendResult | null;
  emailError:         string | null;
  openConfirmModal:   () => void;
  closeConfirmModal:  () => void;
  confirmarYEnviar:   () => Promise<void>;
  setRespuestaActual: (texto: string) => void;
  submitRespuesta: () => Promise<void>;
  resetRespuesta: () => void;
  cambiarEstado: (nuevoEstado: TicketEstado) => Promise<void>;
  actualizarCiudadano: (nombre: string, email: string, telefono?: string) => Promise<void>;
}

export function useTicketDetail(idTicket: string): UseTicketDetailReturn {
  const router = useRouter();
  const [ticket, setTicket] = useState<TicketConUrgencia | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [respuestaActual, setRespuestaActual] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [submitSuccess, setSubmitSuccess] = useState<boolean>(false);
  const [resumenCargando, setResumenCargando] = useState(false);
  const [resumenError, setResumenError] = useState<string | null>(null);
  const [isConfirmModalOpen, setIsConfirmModalOpen] = useState(false);
  const [emailSendResult,    setEmailSendResult]    = useState<EmailSendResult | null>(null);

  const { enviarRespuestaOficial, isSendingRespuesta, error: emailErrorRaw } = useEmailSender();
  const dataMode = useDataMode();

  const idSecretariaActivo = useIdSecretariaActivo();
  const usuario = useAuthStore((s) => s.usuario);
  const iaHabilitada = process.env.NEXT_PUBLIC_IA_HABILITADA === 'true';
  const resumenFetchGen = useRef(0);

  // 1. Carga inicial del ticket
  useEffect(() => {
    async function loadTicket() {
      if (!idTicket || !idSecretariaActivo) return;

      setIsLoading(true);
      setError(null);

      try {
        const response = await getTicketById(idTicket, idSecretariaActivo, dataMode);

        if (response.error) {
          if (response.error === 'ACCESO_DENEGADO') {
            setError('No tienes permisos para ver este ticket');
          } else if (response.error === 'NOT_FOUND') {
            setError('El ticket solicitado no existe');
          } else {
            setError(response.error);
          }
          setTicket(null);
        } else if (response.data) {
          const enriched = enriquecerTicketConUrgencia(response.data);
          setTicket(enriched);
          // Inicializa respuesta con la sugerencia de la IA
          setRespuestaActual(enriched.respuestaSugerida ?? '');
        }
      } catch {
        setError('Error inesperado al cargar el ticket');
      } finally {
        setIsLoading(false);
      }
    }

    loadTicket();
  }, [idTicket, idSecretariaActivo, dataMode]);

  // Resumen ejecutivo GovTech vía gateway (mismo criterio que el panel IA)
  useEffect(() => {
    if (!ticket || !iaHabilitada || !usuario) {
      setResumenCargando(false);
      setResumenError(null);
      return;
    }

    const gen = ++resumenFetchGen.current;
    const ac = new AbortController();

    setResumenCargando(true);
    setResumenError(null);

    const secretariaNombre =
      SECRETARIAS_MOCK.find((s) => s.idSecretaria === ticket.idSecretaria)?.nombre ||
      'Alcaldía de Medellín';

    (async () => {
      try {
        const res = await fetch('/api/ia/resumen-ejecutivo', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          signal: ac.signal,
          body: JSON.stringify({
            contenidoRaw: ticket.contenidoRaw,
            tipoSolicitud: ticket.tipoSolicitud,
            secretariaNombre,
            idTicket: ticket.idTicket,
            duckclawUserId: usuario.idUsuario ?? '',
            duckclawUsername: usuario.nombreCompleto ?? 'Usuario',
          }),
        });

        const data = (await res.json()) as { error?: string; detail?: string; text?: string };

        if (gen !== resumenFetchGen.current) return;

        if (!res.ok) {
          setResumenError(data.detail || data.error || `Error ${res.status}`);
          return;
        }

        const t = (data.text ?? '').trim();
        if (t) {
          setTicket((curr) => (curr ? { ...curr, resumenIa: t } : null));
        }
      } catch (e) {
        if (e instanceof Error && e.name === 'AbortError') return;
        if (gen !== resumenFetchGen.current) return;
        setResumenError(e instanceof Error ? e.message : 'Error al generar resumen');
      } finally {
        if (gen === resumenFetchGen.current) {
          setResumenCargando(false);
        }
      }
    })();

    return () => {
      ac.abort();
    };
    // Solo campos fuente del ticket — no incluir `resumenIa` ni el objeto `ticket` completo para no re-disparar al fusionar el resumen del gateway.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- ticket/usuario coherentes con esta lista primitiva en cada ejecución
  }, [
    ticket?.idTicket,
    ticket?.contenidoRaw,
    ticket?.tipoSolicitud,
    ticket?.idSecretaria,
    iaHabilitada,
    usuario?.idUsuario,
    usuario?.nombreCompleto,
  ]);

  const submitRespuesta = async () => {
    // Esta función ahora simplemente abre el modal si es válido
    openConfirmModal();
  };

  const openConfirmModal = useCallback(() => {
    // Valida antes de abrir el modal
    if (respuestaActual.trim().length < 50) {
      setError('La respuesta debe tener al menos 50 caracteres antes de enviar.');
      return;
    }
    setError(null);
    setIsConfirmModalOpen(true);
  }, [respuestaActual]);

  const closeConfirmModal = useCallback(() => {
    setIsConfirmModalOpen(false);
  }, []);

  const confirmarYEnviar = useCallback(async () => {
    if (!ticket || !idSecretariaActivo) return;
    
    setIsConfirmModalOpen(false);
    setIsSubmitting(true);
    setError(null);
    setEmailSendResult(null);

    const trimmedRespuesta = respuestaActual.trim();

    try {
      // 1. Guardar localmente (en el mock/DB)
      const response = await actualizarRespuesta(idTicket, trimmedRespuesta, idSecretariaActivo, dataMode);
      
      if (response.error) {
        setError(response.error);
        setIsSubmitting(false);
        return;
      }

      setTicket((curr) =>
        curr
          ? {
              ...curr,
              respuestaSugerida: trimmedRespuesta,
              estado: 'Resuelto',
            }
          : null
      );
      router.refresh();

      // 2. Si el ciudadano es anónimo o no tiene email válido, no enviamos email
      const emailLimpio = ticket.emailCiudadano?.trim();
      if (!emailLimpio) {
        setSubmitSuccess(true);
        setIsSubmitting(false);
        return;
      }

      // 3. Construir payload para la API Route
      const fechaFormateada = format(new Date(), "d 'de' MMMM 'de' yyyy", { locale: es });
      const secretariaNombre = SECRETARIAS_MOCK.find(s => s.idSecretaria === ticket.idSecretaria)?.nombre || '';

      const payload: RespuestaEmailPayload = {
        idTicket:          ticket.idTicket,
        numeroRadicado:    ticket.numeroRadicado,
        emailCiudadano:    emailLimpio,
        nombreCiudadano:   ticket.nombreCiudadano,
        tipoSolicitud:     ticket.tipoSolicitud,
        secretariaNombre:  secretariaNombre,
        nombreFuncionario: usuario?.nombreCompleto   ?? 'Funcionario',
        cargoFuncionario:  usuario?.cargo            ?? 'Profesional',
        textoRespuesta:    trimmedRespuesta,
        fechaRespuesta:    fechaFormateada,
      };

      // 4. Enviar
      const result = await enviarRespuestaOficial(payload);
      setEmailSendResult(result);
      
      if (result?.success) {
        setSubmitSuccess(true);
      } else {
        setError(result?.error || 'No se pudo enviar el correo electrónico. Verifique la configuración SMTP.');
      }

    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al procesar el envío de la respuesta');
    } finally {
      setIsSubmitting(false);
    }
  }, [ticket, idTicket, idSecretariaActivo, dataMode, respuestaActual, usuario, enviarRespuestaOficial, router]);

  // 3. Resetear cambios
  const resetRespuesta = useCallback(() => {
    if (ticket) {
      setRespuestaActual(ticket.respuestaSugerida ?? '');
    }
  }, [ticket]);

  // 4. Detección de cambios sin guardar
  const hasUnsavedChanges = respuestaActual !== (ticket?.respuestaSugerida ?? '');

  const cambiarEstado = useCallback(async (nuevoEstado: TicketEstado) => {
    if (!ticket || !idSecretariaActivo) return;
    setIsSubmitting(true);
    try {
      const { actualizarEstadoTicket } = await import('@/services/ticketService');
      await actualizarEstadoTicket(ticket.idTicket, nuevoEstado, idSecretariaActivo, dataMode);
      setTicket(curr => curr ? { ...curr, estado: nuevoEstado } : null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al cambiar estado');
    } finally {
      setIsSubmitting(false);
    }
  }, [ticket, idSecretariaActivo, dataMode]);

  const actualizarCiudadano = useCallback(async (nombre: string, email: string, telefono?: string) => {
    if (!ticket || !idSecretariaActivo) return;
    setIsSubmitting(true);
    try {
      const res = await fetch(`/api/tickets/${ticket.idTicket}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          nombreCiudadano: nombre,
          emailCiudadano: email,
          telefonoCiudadano: telefono
        })
      });

      if (!res.ok) throw new Error('Fallo al actualizar datos del ciudadano');

      setTicket(curr => curr ? { 
        ...curr, 
        nombreCiudadano: nombre, 
        emailCiudadano: email, 
        telefonoCiudadano: telefono 
      } : null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al actualizar ciudadano');
      throw e;
    } finally {
      setIsSubmitting(false);
    }
  }, [ticket, idSecretariaActivo]);

  return {
    ticket,
    isLoading,
    error,
    respuestaActual,
    isSubmitting,
    submitSuccess,
    hasUnsavedChanges,
    resumenCargando,
    resumenError,
    isConfirmModalOpen,
    isSendingEmail: isSendingRespuesta,
    emailSendResult,
    emailError: emailErrorRaw,
    openConfirmModal,
    closeConfirmModal,
    confirmarYEnviar,
    setRespuestaActual,
    submitRespuesta,
    resetRespuesta,
    cambiarEstado,
    actualizarCiudadano,
  };
}
