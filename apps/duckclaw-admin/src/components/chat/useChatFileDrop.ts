'use client';

import { useCallback, useEffect, useState } from 'react';
import type { DragEvent } from 'react';

import { CHAT_IMAGE_MIME } from '@/components/chat/useChatImageAttachments';
import { isAllowedChatDocument } from '@/lib/chatDocumentAttachments';
import { desktopLocalPathsToFiles } from '@/lib/desktopLocalFiles';
import { isTauriDesktop } from '@/lib/tauriRuntime';

type IngestFn = (files: FileList | readonly File[] | null) => Promise<void>;

export type UseChatFileDropOptions = {
  enabled: boolean;
  ingestImages: IngestFn;
  ingestDocuments: IngestFn;
  setAttachError: (message: string | null) => void;
};

function dragLooksLikeFiles(event: DragEvent<HTMLElement>): boolean {
  const types = Array.from(event.dataTransfer?.types || []);
  if (types.includes('Files')) return true;
  // WebView2 / Explorer a veces no expone "Files" hasta el drop.
  return types.length === 0;
}

async function ingestMixedFiles(
  files: File[],
  ingestImages: IngestFn,
  ingestDocuments: IngestFn,
  setAttachError: (message: string | null) => void
) {
  if (files.length === 0) return;
  const images = files.filter((file) => CHAT_IMAGE_MIME.has((file.type || '').toLowerCase()));
  const documents = files.filter((file) => !CHAT_IMAGE_MIME.has((file.type || '').toLowerCase()));
  if (images.length > 0) await ingestImages(images);
  if (documents.length > 0) await ingestDocuments(documents);
  const unsupported = documents.filter((file) => !isAllowedChatDocument(file));
  if (unsupported.length > 0 && images.length === 0) {
    setAttachError(
      'Formato no admitido. Arrastra PDF, Word, Excel, CSV, TXT, MD, PowerPoint, HTML o imágenes.'
    );
  }
}

/**
 * Drop de archivos para el chat.
 * - HTML5 DnD (browser / Tauri con dragDropEnabled=false)
 * - Eventos nativos Tauri (por defecto el shell intercepta el drop HTML5)
 */
export function useChatFileDrop({
  enabled,
  ingestImages,
  ingestDocuments,
  setAttachError,
}: UseChatFileDropOptions) {
  const [dragActive, setDragActive] = useState(false);
  const [dragDepth, setDragDepth] = useState(0);

  const resetDrag = useCallback(() => {
    setDragDepth(0);
    setDragActive(false);
  }, []);

  const onDragEnter = useCallback(
    (event: DragEvent<HTMLElement>) => {
      if (!enabled || !dragLooksLikeFiles(event)) return;
      event.preventDefault();
      event.stopPropagation();
      setDragDepth((depth) => {
        const next = depth + 1;
        setDragActive(true);
        return next;
      });
    },
    [enabled]
  );

  const onDragLeave = useCallback(
    (event: DragEvent<HTMLElement>) => {
      if (!enabled || !dragLooksLikeFiles(event)) return;
      event.preventDefault();
      event.stopPropagation();
      setDragDepth((depth) => {
        const next = Math.max(0, depth - 1);
        if (next === 0) setDragActive(false);
        return next;
      });
    },
    [enabled]
  );

  const onDragOver = useCallback(
    (event: DragEvent<HTMLElement>) => {
      if (!enabled) return;
      // Siempre prevenir default si hay drag: si no, el drop no dispara.
      event.preventDefault();
      event.stopPropagation();
      event.dataTransfer.dropEffect = 'copy';
      if (dragLooksLikeFiles(event) && !dragActive) setDragActive(true);
    },
    [dragActive, enabled]
  );

  const onDrop = useCallback(
    async (event: DragEvent<HTMLElement>) => {
      if (!enabled) return;
      event.preventDefault();
      event.stopPropagation();
      resetDrag();
      const files = Array.from(event.dataTransfer.files || []);
      if (files.length === 0) return;
      try {
        await ingestMixedFiles(files, ingestImages, ingestDocuments, setAttachError);
      } catch (err) {
        setAttachError(err instanceof Error ? err.message : 'No se pudieron adjuntar los archivos');
      }
    },
    [enabled, ingestDocuments, ingestImages, resetDrag, setAttachError]
  );

  useEffect(() => {
    if (!enabled || !isTauriDesktop()) return;
    let cancelled = false;
    let unlisten: (() => void) | undefined;

    void (async () => {
      try {
        const { getCurrentWebview } = await import('@tauri-apps/api/webview');
        unlisten = await getCurrentWebview().onDragDropEvent((event) => {
          if (cancelled) return;
          const kind = event.payload.type;
          if (kind === 'enter' || kind === 'over') {
            setDragActive(true);
            return;
          }
          if (kind === 'leave') {
            resetDrag();
            return;
          }
          if (kind !== 'drop') return;
          resetDrag();
          const paths = Array.isArray(event.payload.paths) ? event.payload.paths : [];
          void (async () => {
            try {
              const files = await desktopLocalPathsToFiles(paths);
              await ingestMixedFiles(files, ingestImages, ingestDocuments, setAttachError);
            } catch (err) {
              setAttachError(
                err instanceof Error ? err.message : 'No se pudieron adjuntar los archivos'
              );
            }
          })();
        });
      } catch {
        // Sin API Tauri: se queda el HTML5 DnD.
      }
    })();

    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, [enabled, ingestDocuments, ingestImages, resetDrag, setAttachError]);

  return {
    dragActive,
    dropProps: {
      onDragEnter,
      onDragLeave,
      onDragOver,
      onDrop: (event: DragEvent<HTMLElement>) => {
        void onDrop(event);
      },
    },
  };
}
