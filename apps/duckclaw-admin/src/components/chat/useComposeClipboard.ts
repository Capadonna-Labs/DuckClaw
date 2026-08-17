'use client';

import { useCallback, type ClipboardEvent, type RefObject } from 'react';
import {
  CHAT_IMAGE_MIME,
  imageFilesFromClipboardData,
  nonImageFilesFromClipboardData,
} from '@/components/chat/useChatImageAttachments';
import { isAllowedChatDocument } from '@/lib/chatDocumentAttachments';

type ComposeClipboardDeps = {
  canSend: boolean;
  input: string;
  setInput: (value: string | ((prev: string) => string)) => void;
  inputRef: RefObject<HTMLTextAreaElement | null>;
  ingestFiles: (files: FileList | readonly File[] | null) => Promise<void>;
  ingestDocuments?: (files: FileList | readonly File[] | null) => Promise<void>;
  setAttachError: (message: string | null) => void;
};

function insertTextAtSelection(
  inputRef: RefObject<HTMLTextAreaElement | null>,
  currentInput: string,
  setInput: ComposeClipboardDeps['setInput'],
  text: string
) {
  const el = inputRef.current;
  if (el) {
    const start = el.selectionStart ?? currentInput.length;
    const end = el.selectionEnd ?? currentInput.length;
    const next = currentInput.slice(0, start) + text + currentInput.slice(end);
    setInput(next);
    window.requestAnimationFrame(() => {
      const pos = start + text.length;
      el.focus();
      el.setSelectionRange(pos, pos);
    });
    return;
  }
  setInput((prev) => prev + text);
}

async function readImageFilesFromSystemClipboard(): Promise<File[]> {
  if (typeof navigator === 'undefined' || !navigator.clipboard?.read) return [];
  const files: File[] = [];
  const items = await navigator.clipboard.read();
  for (const item of items) {
    for (const type of item.types) {
      if (!CHAT_IMAGE_MIME.has(type)) continue;
      const blob = await item.getType(type);
      const ext =
        type === 'image/png' ? 'png' : type === 'image/webp' ? 'webp' : 'jpg';
      files.push(new File([blob], `portapapeles-${Date.now()}.${ext}`, { type }));
    }
  }
  return files;
}

/** Pegado en textarea: texto nativo + imágenes del portapapeles como adjuntos. */
export function useComposeClipboard({
  canSend,
  input,
  setInput,
  inputRef,
  ingestFiles,
  ingestDocuments,
  setAttachError,
}: ComposeClipboardDeps) {
  const onTextareaPaste = useCallback(
    (event: ClipboardEvent<HTMLTextAreaElement>) => {
      if (!canSend) return;
      const imageFiles = imageFilesFromClipboardData(event.clipboardData);
      const otherFiles = nonImageFilesFromClipboardData(event.clipboardData);
      if (imageFiles.length > 0) {
        event.preventDefault();
        void ingestFiles(imageFiles);
        return;
      }
      if (otherFiles.length > 0) {
        event.preventDefault();
        const docs = otherFiles.filter(isAllowedChatDocument);
        const rejected = otherFiles.filter((f) => !isAllowedChatDocument(f));
        if (docs.length > 0 && ingestDocuments) {
          void ingestDocuments(docs);
        }
        if (rejected.length > 0 || (docs.length > 0 && !ingestDocuments)) {
          const names = (rejected.length ? rejected : otherFiles)
            .map((f) => f.name)
            .filter(Boolean)
            .join(', ');
          setAttachError(
            names
              ? `Adjunto «${names}»: usa Archivo (PDF/Word/Excel…) o Imagen (JPEG/PNG/WebP).`
              : 'Formato no admitido en el chat.'
          );
        }
      }
    },
    [canSend, ingestDocuments, ingestFiles, setAttachError]
  );

  const pasteFromClipboard = useCallback(async () => {
    if (!canSend) return;
    setAttachError(null);
    try {
      const imageFiles = await readImageFilesFromSystemClipboard();
      if (imageFiles.length > 0) {
        await ingestFiles(imageFiles);
        return;
      }
    } catch {
      /* Sin permiso de lectura rica o portapapeles sin imagen — intentar texto. */
    }

    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard?.read) {
        const items = await navigator.clipboard.read();
        const docNames: string[] = [];
        for (const item of items) {
          for (const type of item.types) {
            if (CHAT_IMAGE_MIME.has(type)) continue;
            if (type.startsWith('text/')) continue;
            docNames.push(type);
          }
        }
        if (docNames.length > 0) {
          setAttachError(
            'El portapapeles tiene archivos no imagen. Usa Ctrl+V en el cuadro de texto o adjunta JPEG/PNG/WebP.'
          );
          return;
        }
      }
    } catch {
      /* ignore */
    }

    try {
      const text = await navigator.clipboard.readText();
      if (!text) return;
      insertTextAtSelection(inputRef, input, setInput, text);
    } catch {
      setAttachError(
        'No se pudo leer el portapapeles. Usa Ctrl+V en el cuadro de texto o concede permiso al sitio.'
      );
    }
  }, [canSend, ingestFiles, input, inputRef, setAttachError, setInput]);

  return { onTextareaPaste, pasteFromClipboard };
}
