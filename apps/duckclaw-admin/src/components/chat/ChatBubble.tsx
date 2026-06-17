'use client';

import { useCallback, useEffect, useState } from 'react';
import { Check, Copy, Mic, Pencil, RotateCcw, Volume2 } from 'lucide-react';
import { ArtifactImageLightbox } from '@/components/chat/ArtifactImageLightbox';
import { ChatMarkdown, looksLikeMarkdown } from '@/components/chat/ChatMarkdown';
import { playTtsAudio, primeAudioPlayback } from '@/lib/playTtsAudio';
import type { ChatImagePreview, ChatMsg } from '@/components/chat/types';
import {
  formatToolDurationMs,
  parseToolNameFromHeartbeatText,
} from '@/lib/toolHeartbeat';

export function formatChatIdentityPrefix(workerId?: string, swarmSlot = 1): string {
  const slot = Number.isFinite(swarmSlot) && swarmSlot >= 1 ? Math.floor(swarmSlot) : 1;
  const workerLabel = (workerId || '').trim();
  return workerLabel ? `${workerLabel} ${slot}` : String(slot);
}

/** Quita prefijo duplicado en heartbeat (UI ya muestra worker + tipo). */
function ToolHeartbeatBody({ message: m }: { message: ChatMsg }) {
  const toolName =
    (m.toolName || '').trim() || parseToolNameFromHeartbeatText(m.text || '') || 'tool';
  const running =
    m.toolPhase === 'running' ||
    m.toolPhase === 'start' ||
    (m.heartbeatKind === 'tool' && m.toolPhase !== 'done' && m.toolPhase !== 'error');
  const [liveMs, setLiveMs] = useState<number | null>(null);

  useEffect(() => {
    if (!running) {
      setLiveMs(m.toolElapsedMs ?? null);
      return;
    }
    const t0 = m.toolStartedAt ?? Date.now();
    const tick = () => setLiveMs(Math.max(0, Date.now() - t0));
    tick();
    const id = window.setInterval(tick, 50);
    return () => window.clearInterval(id);
  }, [running, m.toolStartedAt, m.toolElapsedMs, m.toolPhase]);

  const durMs = running ? liveMs : (m.toolElapsedMs ?? liveMs);
  const dur = formatToolDurationMs(durMs);
  return (
    <span className="block whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
      {`Usando: ${toolName}`}
      {dur ? ` · ${dur}` : running ? ' · en curso' : ''}
    </span>
  );
}

export function stripHeartbeatBodyPrefix(
  text: string,
  workerId?: string,
  swarmSlot = 1
): string {
  let body = (text || '').trim();
  if (!body) return body;

  const identity = formatChatIdentityPrefix(workerId, swarmSlot);
  if (identity) {
    const esc = identity.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    body = body.replace(new RegExp(`^${esc}(?:\\s*[—–-]\\s*)?`, 'u'), '').trim();
  }

  const workerBase = (workerId || '').trim();
  if (workerBase) {
    const escBase = workerBase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    body = body
      .replace(new RegExp(`^\\*\\*${escBase}(?:\\s+\\d+)?\\s*·[^*]+\\*\\*\\s*`, 'iu'), '')
      .trim();
  }
  return body;
}

export function ChatBubble({
  message: m,
  onRetry,
  canRetry = false,
  onEdit,
  canEdit = false,
}: {
  message: ChatMsg;
  /** Reenvía el mensaje de usuario asociado a este turno. */
  onRetry?: () => void;
  canRetry?: boolean;
  /** Carga el mensaje de usuario en el input para editar y reenviar. */
  onEdit?: () => void;
  canEdit?: boolean;
}) {
  const isUser = m.role === 'user';
  const isError = m.role === 'error';
  const isHeartbeat = m.role === 'heartbeat';
  const isInterrupted = Boolean(m.interrupted);
  const isAssistant = m.role === 'assistant';
  const displayText =
    isHeartbeat && m.text
      ? stripHeartbeatBodyPrefix(m.text, m.workerId, m.swarmSlot ?? 1)
      : m.text;
  const hasCopyableText = Boolean((displayText || '').trim());
  const canCopy =
    !m.streaming && !isHeartbeat && hasCopyableText && (isAssistant || isUser);
  const showActions =
    canCopy || (canRetry && Boolean(onRetry)) || (canEdit && Boolean(onEdit));
  const actionsAlwaysVisible = canCopy && (isAssistant || isError);
  const [copied, setCopied] = useState(false);
  const [lightboxImage, setLightboxImage] = useState<ChatImagePreview | null>(null);
  const heartbeatLabel =
    m.heartbeatKind === 'plan'
      ? 'Plan'
      : m.heartbeatKind === 'tool'
        ? 'Herramienta'
        : m.heartbeatKind === 'visual'
          ? 'Imagen'
          : 'Progreso';

  const copyText = useCallback(async () => {
    if (!displayText?.trim()) return;
    const text = displayText;
    let ok = false;
    try {
      if (window.isSecureContext && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        ok = true;
      }
    } catch {
      ok = false;
    }
    if (!ok) {
      try {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', '');
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        ok = document.execCommand('copy');
        document.body.removeChild(ta);
      } catch {
        ok = false;
      }
    }
    if (ok) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    }
  }, [displayText]);

  const isEmptyAssistantShell =
    !isUser &&
    !isError &&
    !isHeartbeat &&
    !isInterrupted &&
    m.streaming &&
    !(displayText || '').trim() &&
    !(m.imagePreviews?.length);
  if (isEmptyAssistantShell) return null;

  return (
    <div
      className={`group relative max-w-[90%] max-sm:max-w-full max-sm:w-full min-w-0 rounded-2xl px-4 py-3 text-sm overflow-hidden ${
        isUser
          ? 'ml-auto bg-gov-blue-700 text-white'
          : isError
            ? 'bg-red-50 text-red-800 border border-red-200 whitespace-pre-wrap dark:bg-red-950/30 dark:text-red-300 dark:border-red-900'
            : isHeartbeat
              ? 'mx-auto w-full max-w-full bg-sky-50 text-sky-950 border border-sky-200/80 dark:bg-sky-950/25 dark:text-sky-100 dark:border-sky-800/60'
              : isInterrupted
                ? 'bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/50 text-amber-900 dark:text-amber-200'
                : 'bg-gov-gray-50 dark:bg-dark-bg border dark:border-dark-border'
      } ${showActions ? 'pr-[4.25rem]' : ''}`}
    >
      {showActions && (
        <div
          className={`absolute top-2 right-2 flex items-center gap-0.5 transition-opacity ${
            actionsAlwaysVisible
              ? 'opacity-100'
              : 'opacity-0 group-hover:opacity-100 focus-within:opacity-100 max-sm:opacity-100'
          }`}
        >
          {canEdit && onEdit && (
            <button
              type="button"
              onClick={onEdit}
              className={`p-1 rounded-md ${
                isUser
                  ? 'text-white/80 hover:bg-white/15'
                  : 'text-gov-gray-400 hover:bg-gov-gray-200/80 dark:hover:bg-dark-border'
              }`}
              aria-label="Editar mensaje"
              title="Editar"
            >
              <Pencil size={14} aria-hidden />
            </button>
          )}
          {canRetry && onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className={`p-1 rounded-md ${
                isUser
                  ? 'text-white/80 hover:bg-white/15'
                  : 'text-gov-gray-400 hover:bg-gov-gray-200/80 dark:hover:bg-dark-border'
              }`}
              aria-label="Reintentar mensaje"
              title="Reintentar"
            >
              <RotateCcw size={14} aria-hidden />
            </button>
          )}
          {canCopy && (
            <button
              type="button"
              onClick={() => void copyText()}
              className={`p-1 rounded-md ${
                isUser
                  ? 'text-white/80 hover:bg-white/15'
                  : 'text-gov-gray-400 hover:bg-gov-gray-200/80 dark:hover:bg-dark-border'
              }`}
              aria-label={copied ? 'Copiado' : 'Copiar mensaje'}
              title={copied ? 'Copiado' : 'Copiar'}
            >
              {copied ? <Check size={14} aria-hidden /> : <Copy size={14} aria-hidden />}
            </button>
          )}
        </div>
      )}
      {isHeartbeat && (
        <p className="text-[10px] font-bold uppercase tracking-wider text-sky-700/90 dark:text-sky-300/90 mb-1">
          <span className="normal-case text-sky-800 dark:text-sky-200">
            {formatChatIdentityPrefix(m.workerId, m.swarmSlot ?? 1)}
          </span>
          {' · '}
          {heartbeatLabel}
        </p>
      )}
      {m.imagePreviews && m.imagePreviews.length > 0 && (
        <div className={`flex flex-wrap gap-2 ${displayText?.trim() ? 'mb-2' : ''}`}>
          {m.imagePreviews.map((img) => (
            <button
              key={img.url}
              type="button"
              onClick={() => setLightboxImage(img)}
              className="block p-0 border-0 bg-transparent cursor-zoom-in rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-gov-blue-500"
              aria-label={`Ver imagen ampliada: ${img.name || 'imagen'}`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={img.url}
                alt={img.name}
                className={
                  isUser
                    ? 'max-h-32 max-w-full rounded-lg border border-white/20 object-contain'
                    : 'max-h-64 max-w-full rounded-lg border border-gov-gray-200 dark:border-dark-border object-contain hover:opacity-90 transition-opacity'
                }
              />
            </button>
          ))}
        </div>
      )}
      <ArtifactImageLightbox image={lightboxImage} onClose={() => setLightboxImage(null)} />
      {isHeartbeat && m.heartbeatKind === 'tool' ? (
        <ToolHeartbeatBody message={m} />
      ) : isUser || isError || isInterrupted || isHeartbeat ? (
        displayText?.trim() ? (
          isUser && looksLikeMarkdown(displayText) ? (
            <div className="min-w-0">
              {m.voiceNote ? (
                <span className="inline-flex items-center gap-1 mb-1 opacity-90" title="Nota de voz">
                  <Mic size={14} aria-hidden />
                </span>
              ) : null}
              <ChatMarkdown content={displayText} variant="user" />
            </div>
          ) : (
            <span className="block whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
              {isUser && m.voiceNote ? (
                <span className="inline-flex items-center gap-1 mr-1 opacity-90" title="Nota de voz">
                  <Mic size={14} aria-hidden />
                </span>
              ) : null}
              {displayText}
            </span>
          )
        ) : null
      ) : (
        <>
          <ChatMarkdown content={displayText} />
          {isAssistant && m.audioBase64 ? (
            <button
              type="button"
              onClick={() => {
                primeAudioPlayback();
                void playTtsAudio(m.audioBase64!, {
                  format: m.audioFormat,
                  source: 'replay-button',
                }).then((r) => {
                  if (!r.ok && typeof window !== 'undefined') {
                    window.alert(
                      r.isIOS && r.mime.includes('ogg')
                        ? 'Safari en iOS no reproduce OGG. El servidor debe devolver WAV.'
                        : `No se pudo reproducir el audio (${r.reason}).`
                    );
                  }
                });
              }}
              className="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-gov-gray-200 dark:border-dark-border px-2.5 py-1 text-xs font-semibold text-gov-gray-700 dark:text-dark-muted hover:bg-gov-gray-100 dark:hover:bg-dark-border"
              aria-label="Escuchar respuesta"
            >
              <Volume2 size={14} aria-hidden />
              Escuchar respuesta
            </button>
          ) : null}
          {isAssistant && m.audioPlayError ? (
            <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">
              No se pudo reproducir automáticamente. Pulsa «Escuchar respuesta».
            </p>
          ) : null}
          {isAssistant && m.audioUnavailable && !m.audioBase64 ? (
            <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">Audio no disponible (TTS).</p>
          ) : null}
          {m.streaming && displayText && (
            <span className="inline-block w-2 h-4 ml-0.5 bg-gov-blue-600 animate-pulse align-middle" />
          )}
        </>
      )}
    </div>
  );
}

export type ThinkingDotsProps = {
  /** Tamaño visual: sm (FAB), md (burbuja en panel). */
  size?: 'sm' | 'md';
  className?: string;
};

/** Tres puntos animados (indicador «pensando»). */
export function ThinkingDots({ size = 'md', className = '' }: ThinkingDotsProps) {
  const dot =
    size === 'sm'
      ? 'size-1.5'
      : 'size-2';
  const gap = size === 'sm' ? 'gap-0.5' : 'gap-1';
  return (
    <span
      className={`inline-flex items-center ${gap} ${className}`}
      aria-hidden
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className={`${dot} rounded-full bg-current animate-bounce`}
          style={{ animationDelay: `${i * 0.15}s`, animationDuration: '0.9s' }}
        />
      ))}
    </span>
  );
}

export type ThinkingBubbleProps = {
  startedAt: number;
  /** Worker activo en el selector (p. ej. platform-orchestrator, ui-designer). */
  workerId?: string;
  /** Instancia swarm 1..n; la base siempre es 1. */
  swarmSlot?: number;
};

export function ThinkingBubble({
  startedAt,
  workerId = '',
  swarmSlot = 1,
}: ThinkingBubbleProps) {
  const [elapsedSec, setElapsedSec] = useState(0);

  useEffect(() => {
    const update = () => {
      const raw = Math.max(0, (Date.now() - startedAt) / 1000);
      setElapsedSec(Math.round(raw * 100) / 100);
    };
    update();
    const id = window.setInterval(update, 50);
    return () => window.clearInterval(id);
  }, [startedAt]);

  const elapsedLabel = elapsedSec.toFixed(2);
  const identityPrefix = formatChatIdentityPrefix(workerId, swarmSlot);

  return (
    <div
      className="max-w-[85%] flex items-center gap-3 rounded-2xl px-4 py-3 bg-gov-gray-50 dark:bg-dark-bg border dark:border-dark-border"
      role="status"
      aria-live="polite"
      aria-label={`${identityPrefix} Pensando, ${elapsedLabel} segundos`}
    >
      <div
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2 border-gov-blue-200 dark:border-gov-blue-900 text-gov-blue-700 dark:text-dark-cyan"
        aria-hidden
      >
        <ThinkingDots size="md" />
      </div>
      <p className="text-sm font-semibold text-gov-gray-700 dark:text-dark-text tabular-nums">
        <span className="text-gov-blue-800 dark:text-dark-cyan">{identityPrefix}</span>{' '}
        Pensando…{' '}
        <span className="font-mono text-gov-gray-500 dark:text-dark-muted">{elapsedLabel}s</span>
      </p>
    </div>
  );
}
