'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, Copy, Mic, Pencil, Reply, RotateCcw, Volume2 } from 'lucide-react';
import { ArtifactImageLightbox } from '@/components/chat/ArtifactImageLightbox';
import { ChatMarkdown, looksLikeMarkdown } from '@/components/chat/ChatMarkdown';
import { playTtsAudio, primeAudioPlayback } from '@/lib/playTtsAudio';
import type { ChatImagePreview, ChatMsg } from '@/components/chat/types';
import { stripContextBlocksForDisplay } from '@/lib/chatMessageImages';
import { splitLeadingSlashCommand } from '@/components/chat/adminChatPure';
import {
  formatChatIdentityPrefix,
  stripChatIdentityNoise,
} from '@/lib/workerOptions';

export function stripHeartbeatBodyPrefix(
  text: string,
  workerId?: string,
  swarmSlot = 1,
  displayName?: string
): string {
  void swarmSlot;
  return stripChatIdentityNoise(text, { workerId, displayName });
}

const SWIPE_MAX_PX = 80;
const SWIPE_QUOTE_PX = 60;

/** "11:45 p. m." today, "18 oct, 11:45 p. m." otherwise. */
export function formatMessageTime(iso: string | undefined, now = new Date()): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const time = d.toLocaleTimeString('es-CO', { hour: 'numeric', minute: '2-digit' });
  return d.toDateString() === now.toDateString()
    ? time
    : `${d.toLocaleDateString('es-CO', { day: 'numeric', month: 'short' })}, ${time}`;
}

export function ChatBubble({
  message: m,
  onRetry,
  canRetry = false,
  onEdit,
  canEdit = false,
  identityLabel = '',
  activeWorkerId = '',
  onQuote,
}: {
  message: ChatMsg;
  /** Deslizar a la derecha: cita el mensaje en el input. */
  onQuote?: () => void;
  /** Reenvía el mensaje de usuario asociado a este turno. */
  onRetry?: () => void;
  canRetry?: boolean;
  /** Carga el mensaje de usuario en el input para editar y reenviar. */
  onEdit?: () => void;
  canEdit?: boolean;
  /** Nombre visible del worker (nunca el worker_id técnico). */
  identityLabel?: string;
  /** worker_id activo (para strip aunque el mensaje no traiga workerId). */
  activeWorkerId?: string;
}) {
  const isUser = m.role === 'user';
  const isError = m.role === 'error';
  const isHeartbeat = m.role === 'heartbeat';
  const isToolHeartbeat = isHeartbeat && m.heartbeatKind === 'tool';
  const isInterrupted = Boolean(m.interrupted);
  const isAssistant = m.role === 'assistant';
  const technicalId = (m.workerId || activeWorkerId || '').trim();
  const displayText = (() => {
    if (!m.text) return m.text;
    if (isHeartbeat || isAssistant) {
      return stripChatIdentityNoise(m.text, {
        workerId: technicalId,
        displayName: identityLabel,
      });
    }
    if (isUser) {
      return stripContextBlocksForDisplay(m.text);
    }
    return m.text;
  })();
  const identityPrefix = formatChatIdentityPrefix(identityLabel);
  const slashCmd = isUser ? splitLeadingSlashCommand(displayText || '') : null;
  const hasCopyableText = Boolean((displayText || '').trim());
  const canCopy =
    !m.streaming && !isHeartbeat && hasCopyableText && (isAssistant || isUser);
  const showActions =
    canCopy || (canRetry && Boolean(onRetry)) || (canEdit && Boolean(onEdit));
  const actionsAlwaysVisible = canCopy && (isAssistant || isError);
  const [copied, setCopied] = useState(false);
  // Live replies have no server time until the history reloads: stamp when streaming ends.
  const [liveTs, setLiveTs] = useState<string | undefined>(undefined);
  const wasStreaming = useRef(Boolean(m.streaming));
  useEffect(() => {
    if (wasStreaming.current && !m.streaming) setLiveTs(new Date().toISOString());
    wasStreaming.current = Boolean(m.streaming);
  }, [m.streaming]);
  const timeLabel = formatMessageTime(m.ts || liveTs);
  const canQuote = Boolean(onQuote) && canCopy;
  const [swipeX, setSwipeX] = useState(0);
  const swipeStart = useRef<{ x: number; y: number; axis: 'x' | 'y' | null } | null>(null);
  const onTouchStart = (e: React.TouchEvent) => {
    // Tables/code blocks scroll sideways: a drag inside them is theirs, not a swipe.
    for (let el = e.target as HTMLElement | null; el && el !== e.currentTarget; el = el.parentElement) {
      if (el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflowX !== 'visible') {
        swipeStart.current = null;
        return;
      }
    }
    const t = e.touches[0];
    swipeStart.current = { x: t.clientX, y: t.clientY, axis: null };
  };
  const onTouchMove = (e: React.TouchEvent) => {
    const start = swipeStart.current;
    if (!start) return;
    const t = e.touches[0];
    const dx = t.clientX - start.x;
    const dy = t.clientY - start.y;
    if (!start.axis && (Math.abs(dx) > 8 || Math.abs(dy) > 8)) {
      start.axis = Math.abs(dx) > Math.abs(dy) * 1.2 ? 'x' : 'y';
    }
    if (start.axis !== 'x') return;
    const min = timeLabel ? -SWIPE_MAX_PX : 0;
    const max = canQuote ? SWIPE_MAX_PX : 0;
    setSwipeX(Math.max(min, Math.min(max, dx)));
  };
  const onTouchEnd = () => {
    if (swipeX >= SWIPE_QUOTE_PX && canQuote) onQuote?.();
    swipeStart.current = null;
    setSwipeX(0);
  };
  const [lightboxImage, setLightboxImage] = useState<ChatImagePreview | null>(null);
  const openLightbox = useCallback((img: ChatImagePreview) => {
    setLightboxImage(img);
  }, []);
  const openMarkdownImage = useCallback((img: { url: string; name: string }) => {
    setLightboxImage({ url: img.url, name: img.name });
  }, []);
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
    !(m.imagePreviews?.length) &&
    !(m.documentNames?.length);
  if (isEmptyAssistantShell) return null;

  // Solo era el prefijo técnico "d 1" / id+slot — no mostrar burbuja vacía.
  const isIdentityOnlyAssistant =
    isAssistant &&
    !m.streaming &&
    !(displayText || '').trim() &&
    !(m.imagePreviews?.length) &&
    !(m.documentNames?.length) &&
    !m.audioBase64;
  if (isIdentityOnlyAssistant) return null;
  if (isToolHeartbeat) return null;

  return (
    <div
      className="relative w-full overflow-x-clip [touch-action:pan-y]"
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={onTouchEnd}
      onTouchCancel={onTouchEnd}
    >
    {swipeX > 0 ? (
      <span
        className="absolute left-1 top-1/2 -translate-y-1/2 text-gov-gray-400 transition-opacity"
        style={{ opacity: Math.min(1, swipeX / SWIPE_QUOTE_PX) }}
        aria-hidden
      >
        <Reply size={18} />
      </span>
    ) : null}
    {swipeX < 0 ? (
      <span
        className="absolute right-1 top-1/2 -translate-y-1/2 whitespace-nowrap text-[11px] tabular-nums text-gov-gray-500 dark:text-dark-muted"
        style={{ opacity: Math.min(1, -swipeX / 40) }}
      >
        {timeLabel}
      </span>
    ) : null}
    <div
      title={timeLabel || undefined}
      style={swipeX ? { transform: `translateX(${swipeX}px)` } : undefined}
      className={`${swipeStart.current?.axis === 'x' ? '' : 'transition-transform duration-200'} group relative max-w-[90%] max-sm:max-w-full max-sm:w-full min-w-0 rounded-2xl px-4 py-3 text-sm overflow-hidden ${
        isUser
          ? 'ml-auto bg-gov-blue-700 text-white'
          : isError
            ? 'bg-red-50 text-red-800 border border-red-200 whitespace-pre-wrap dark:bg-red-950/30 dark:text-red-300 dark:border-red-900'
            : isHeartbeat
              ? 'mx-auto w-full max-w-full bg-sky-50 text-sky-950 border border-sky-200/80 dark:bg-sky-950/25 dark:text-sky-100 dark:border-sky-800/60'
              : isInterrupted
                ? 'bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/50 text-amber-900 dark:text-amber-200'
                : 'bg-gov-gray-50 dark:bg-dark-bg border dark:border-dark-border'
      } ${showActions ? '[&_.chat-markdown>:first-child]:pr-12' : ''}`}
    >
      {showActions && (
        <div
          className={`absolute top-2 right-2 z-10 flex items-center gap-0.5 rounded-lg px-0.5 py-0.5 backdrop-blur-sm transition-opacity ${
            isUser
              ? 'bg-gov-blue-700/90'
              : isError
                ? 'bg-red-50/90 dark:bg-red-950/80'
                : 'bg-gov-gray-50/90 dark:bg-dark-bg/90'
          } ${
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
            {identityPrefix}
          </span>
          {' · '}
          {heartbeatLabel}
        </p>
      )}
      {m.imagePreviews && m.imagePreviews.length > 0 && (
        <div className={`flex flex-wrap gap-2 ${displayText?.trim() || m.documentNames?.length ? 'mb-2' : ''}`}>
          {m.imagePreviews.map((img) => (
            <button
              key={img.url}
              type="button"
              onClick={() => openLightbox(img)}
              className="block p-0 border-0 bg-transparent cursor-zoom-in rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-gov-blue-500"
              aria-label={`Ver imagen ampliada: ${img.name || 'imagen'}`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={img.url}
                alt={img.name}
                // Sandbox runs report every artifact (CSV, JSON, duplicate storage ids);
                // only real images load — hide the rest instead of a broken icon.
                onError={(e) => {
                  const btn = e.currentTarget.parentElement;
                  if (btn) btn.style.display = 'none';
                }}
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
      {m.documentNames && m.documentNames.length > 0 && (
        <div className={`flex flex-wrap gap-1.5 ${displayText?.trim() ? 'mb-2' : ''}`}>
          {m.documentNames.map((name) => (
            <span
              key={name}
              className={
                isUser
                  ? 'inline-flex max-w-[12rem] items-center truncate rounded-md bg-white/15 px-2 py-0.5 text-[11px] font-medium'
                  : 'inline-flex max-w-[12rem] items-center truncate rounded-md border border-gov-gray-200 bg-gov-gray-50 px-2 py-0.5 text-[11px] font-medium dark:border-dark-border dark:bg-dark-bg'
              }
              title={name}
            >
              📎 {name}
            </span>
          ))}
        </div>
      )}
      <ArtifactImageLightbox image={lightboxImage} onClose={() => setLightboxImage(null)} />
      {isUser || isError || isInterrupted || isHeartbeat ? (
        displayText?.trim() ? (
          isUser && looksLikeMarkdown(displayText) ? (
            <div className="min-w-0">
              {m.voiceNote ? (
                <span className="inline-flex items-center gap-1 mb-1 opacity-90" title="Nota de voz">
                  <Mic size={14} aria-hidden />
                </span>
              ) : null}
              <ChatMarkdown
                content={displayText}
                variant="user"
                onImageOpen={openMarkdownImage}
              />
            </div>
          ) : (
            <span className="block whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
              {isUser && m.voiceNote ? (
                <span className="inline-flex items-center gap-1 mr-1 opacity-90" title="Nota de voz">
                  <Mic size={14} aria-hidden />
                </span>
              ) : null}
              {slashCmd ? (
                <>
                  <span className="mr-1.5 inline-block rounded-md bg-white/20 px-1.5 py-0.5 font-mono text-xs font-bold align-middle">
                    {slashCmd.cmd}
                  </span>
                  {slashCmd.rest}
                </>
              ) : (
                displayText
              )}
            </span>
          )
        ) : null
      ) : (
        <>
          <ChatMarkdown content={displayText} onImageOpen={openMarkdownImage} />
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
  /** Nombre visible del worker (nunca el worker_id técnico). */
  identityLabel?: string;
};

export function ThinkingBubble({
  startedAt,
  identityLabel = '',
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
  const identityPrefix = formatChatIdentityPrefix(identityLabel);

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
