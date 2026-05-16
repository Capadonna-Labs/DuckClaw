'use client';

import { useState, useCallback } from 'react';
import { useAuthStore } from '@/store/authStore';
import type {
  ConfirmacionEmailPayload,
  RespuestaEmailPayload,
  EmailSendResult,
  RegistroEmail,
} from '@/types';

interface UseEmailSenderReturn {
  isSendingConfirmacion: boolean;
  isSendingRespuesta:    boolean;
  lastResult:            EmailSendResult | null;
  error:                 string | null;
  historialSesion:       RegistroEmail[];
  enviarConfirmacion:      (payload: ConfirmacionEmailPayload) => Promise<EmailSendResult | null>;
  enviarRespuestaOficial:  (payload: RespuestaEmailPayload)   => Promise<EmailSendResult | null>;
  limpiarError:            () => void;
}

export function useEmailSender(): UseEmailSenderReturn {
  const [isSendingConfirmacion, setIsSendingConfirmacion] = useState(false);
  const [isSendingRespuesta, setIsSendingRespuesta] = useState(false);
  const [lastResult, setLastResult] = useState<EmailSendResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [historialSesion, setHistorialSesion] = useState<RegistroEmail[]>([]);

  const enviarConfirmacion = useCallback(async (payload: ConfirmacionEmailPayload): Promise<EmailSendResult | null> => {
    setIsSendingConfirmacion(true);
    setError(null);

    try {
      const response = await fetch('/api/email/confirmar', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      const result: EmailSendResult = await response.json();

      if (!response.ok) {
        throw new Error(result.error || 'Error al enviar el correo de confirmación');
      }

      setHistorialSesion((prev) => [result.registro, ...prev]);
      setLastResult(result);
      return result;
    } catch (err) {
      const message = err instanceof TypeError 
        ? 'Sin conexión. Verifica tu conexión a internet.' 
        : (err as Error).message;
      setError(message);
      return null;
    } finally {
      setIsSendingConfirmacion(false);
    }
  }, []);

  const enviarRespuestaOficial = useCallback(async (payload: RespuestaEmailPayload): Promise<EmailSendResult | null> => {
    setIsSendingRespuesta(true);
    setError(null);

    try {
      const usuario = useAuthStore.getState().usuario;
      
      const fullPayload: RespuestaEmailPayload = {
        ...payload,
        nombreFuncionario: payload.nombreFuncionario || (usuario?.nombreCompleto ?? 'Funcionario'),
        cargoFuncionario:  payload.cargoFuncionario  || (usuario?.cargo          ?? 'Profesional'),
      };

      const response = await fetch('/api/email/responder', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(fullPayload),
      });

      const result: EmailSendResult = await response.json();

      if (!response.ok) {
        setError(result.error || 'Error al enviar la respuesta oficial');
        return result;
      }

      setHistorialSesion((prev) => [result.registro, ...prev]);
      setLastResult(result);
      return result;
    } catch (err) {
      const message = err instanceof TypeError 
        ? 'Sin conexión. Verifica tu conexión a internet.' 
        : (err as Error).message;
      setError(message);
      return null;
    } finally {
      setIsSendingRespuesta(false);
    }
  }, []);

  const limpiarError = useCallback(() => setError(null), []);

  return {
    isSendingConfirmacion,
    isSendingRespuesta,
    lastResult,
    error,
    historialSesion,
    enviarConfirmacion,
    enviarRespuestaOficial,
    limpiarError,
  };
}
