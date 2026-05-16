'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { Ticket } from '@/types';
import { useAuthStore } from '@/store/authStore';

interface UseIAAssistantProps {
  ticket: Ticket;
  onRespuestaGenerada: (texto: string) => void;
}

export interface SugerenciaRapida {
  label: string;
  instruccion: string;
}

const SUGERENCIAS: SugerenciaRapida[] = [
  { label: '📝 Más formal', instruccion: 'Reescribe el borrador con un tono más formal e institucional' },
  { label: '✂️ Más conciso', instruccion: 'Mantén la misma información pero reduce el texto a la mitad' },
  { label: '💡 Con normativa', instruccion: 'Añade referencias a la normativa colombiana aplicable (Ley 1755 de 2015)' },
  { label: '🔄 Desde cero', instruccion: 'Genera una respuesta completamente nueva basada solo en la solicitud del ciudadano' },
  { label: '🤝 Más empático', instruccion: 'Reescribe con un tono más empático y cercano al ciudadano, sin perder la formalidad' },
];

/**
 * Hook useIAAssistant — proxy `/api/ia/regenerar` → DuckClaw PQRSD-Assistant (JSON).
 */
export function useIAAssistant({ ticket, onRespuestaGenerada }: UseIAAssistantProps) {
  const [instruccion, setInstruccion] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [textoEnStream, setTextoEnStream] = useState('');
  const [error, setError] = useState<string | null>(null);
  /** Tokens reales si el gateway envía usage_tokens; si no, estimación por caracteres. */
  const [tokensUsados, setTokensUsados] = useState(0);
  /** Segundos transcurridos mientras el fetch está en curso (no hay streaming). */
  const [generacionSegundos, setGeneracionSegundos] = useState(0);
  const [ultimaDuracionMs, setUltimaDuracionMs] = useState<number | null>(null);
  /** true cuando el servidor rechazó la instrucción (sin LLM); no se aplica al editor. */
  const [instruccionRechazada, setInstruccionRechazada] = useState(false);

  const abortControllerRef = useRef<AbortController | null>(null);
  const { usuario } = useAuthStore();

  useEffect(() => {
    if (!isGenerating) return;
    setGeneracionSegundos(0);
    const t0 = Date.now();
    const id = window.setInterval(() => {
      setGeneracionSegundos(Math.floor((Date.now() - t0) / 1000));
    }, 400);
    return () => window.clearInterval(id);
  }, [isGenerating]);

  const cancelar = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsGenerating(false);
    if (textoEnStream) {
      onRespuestaGenerada(textoEnStream);
    }
  }, [textoEnStream, onRespuestaGenerada]);

  const regenerar = useCallback(async () => {
    if (!instruccion.trim()) return;

    setIsGenerating(true);
    setTextoEnStream('');
    setError(null);
    setInstruccionRechazada(false);
    setTokensUsados(0);
    setUltimaDuracionMs(null);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const response = await fetch('/api/ia/regenerar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contenidoRaw: ticket.contenidoRaw,
          resumenIa: ticket.resumenIa,
          respuestaActual: ticket.respuestaSugerida ?? '',
          instruccionFuncionario: instruccion,
          secretariaNombre: usuario?.secretariaNombre || 'Alcaldía de Medellín',
          tipoSolicitud: ticket.tipoSolicitud,
          idTicket: ticket.idTicket,
          duckclawUserId: usuario?.idUsuario ?? '',
          duckclawUsername: usuario?.nombreCompleto ?? 'Usuario',
        }),
        signal: controller.signal,
      });

      const contentType = response.headers.get('content-type') || '';

      if (contentType.includes('application/json')) {
        const data = (await response.json()) as {
          error?: string;
          detail?: string;
          text?: string;
          invalid_request?: boolean;
          elapsed_ms?: number;
          usage_tokens?: { total_tokens?: number; input_tokens?: number; output_tokens?: number };
        };
        if (!response.ok) {
          throw new Error(data.error || data.detail || 'Error al conectar con el gateway');
        }
        const t = (data.text ?? '').trim();
        if (!t) {
          throw new Error('Respuesta vacía del asistente');
        }
        setTextoEnStream(t);
        if (data.invalid_request === true) {
          setInstruccionRechazada(true);
          setTokensUsados(0);
          setUltimaDuracionMs(0);
          return;
        }
        setInstruccionRechazada(false);
        const tok = data.usage_tokens?.total_tokens;
        setTokensUsados(
          typeof tok === 'number' && tok > 0 ? tok : Math.max(1, Math.ceil(t.length / 4))
        );
        if (typeof data.elapsed_ms === 'number' && data.elapsed_ms >= 0) {
          setUltimaDuracionMs(data.elapsed_ms);
        }
        onRespuestaGenerada(t);
        return;
      }

      if (!response.ok) {
        const errData = (await response.json()) as { error?: string };
        throw new Error(errData.error || 'Error al conectar con el servidor de IA');
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let textoAcumulado = '';

      if (!reader) throw new Error('No se pudo leer la respuesta');

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6).trim();

            if (data === '[DONE]') {
              onRespuestaGenerada(textoAcumulado);
              continue;
            }

            try {
              const parsed = JSON.parse(data) as { text?: string; error?: string };
              if (parsed.text) {
                textoAcumulado += parsed.text;
                setTextoEnStream(textoAcumulado);
                setTokensUsados(Math.ceil(textoAcumulado.length / 4));
              }
              if (parsed.error) throw new Error(parsed.error);
            } catch {
              /* ignore chunk parse noise */
            }
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        console.log('Generación de IA cancelada por el funcionario.');
      } else {
        const message = err instanceof Error ? err.message : 'Error desconocido en el servicio de IA';
        setError(message);
      }
    } finally {
      setIsGenerating(false);
      abortControllerRef.current = null;
    }
  }, [instruccion, ticket, usuario, onRespuestaGenerada]);

  return {
    instruccion,
    setInstruccion,
    isGenerating,
    textoEnStream,
    error,
    instruccionRechazada,
    tokensUsados,
    generacionSegundos,
    ultimaDuracionMs,
    regenerar,
    cancelar,
    sugerenciasRapidas: SUGERENCIAS,
  };
}
