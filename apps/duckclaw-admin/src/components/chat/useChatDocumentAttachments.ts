'use client';

import { useCallback, useRef, useState } from 'react';
import {
  CHAT_DOCUMENT_ACCEPT,
  guessChatDocumentMime,
  isAllowedChatDocument,
} from '@/lib/chatDocumentAttachments';

export {
  CHAT_DOCUMENT_ACCEPT,
  CHAT_DOCUMENT_EXTENSIONS,
  isAllowedChatDocument,
} from '@/lib/chatDocumentAttachments';

const DEFAULT_MAX_BYTES = 5 * 1024 * 1024;
const DEFAULT_MAX_COUNT = 5;

export type PendingChatDocument = {
  id: string;
  name: string;
  mime_type: string;
  data_base64: string;
  size: number;
};

export type ChatDocumentPayload = {
  filename: string;
  mime_type: string;
  data_base64: string;
};

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const raw = String(reader.result || '');
      const comma = raw.indexOf(',');
      resolve(comma >= 0 ? raw.slice(comma + 1) : raw);
    };
    reader.onerror = () => reject(new Error('No se pudo leer el archivo'));
    reader.readAsDataURL(file);
  });
}

export function useChatDocumentAttachments(
  maxCount = DEFAULT_MAX_COUNT,
  maxBytes = DEFAULT_MAX_BYTES
) {
  const [pending, setPending] = useState<PendingChatDocument[]>([]);
  const [attachError, setAttachError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const clearDocuments = useCallback(() => {
    setPending([]);
    setAttachError(null);
  }, []);

  const removeDocument = useCallback((id: string) => {
    setPending((prev) => prev.filter((p) => p.id !== id));
  }, []);

  const ingestFiles = useCallback(
    async (files: FileList | readonly File[] | null) => {
      const fileList = files
        ? files instanceof FileList
          ? Array.from(files)
          : [...files]
        : [];
      if (fileList.length === 0) return;
      setAttachError(null);
      const next: PendingChatDocument[] = [...pending];
      for (let i = 0; i < fileList.length; i += 1) {
        if (next.length >= maxCount) {
          setAttachError(`Máximo ${maxCount} archivos por mensaje`);
          break;
        }
        const file = fileList[i];
        if (!isAllowedChatDocument(file)) {
          setAttachError('Formato no admitido (PDF, Word, Excel, CSV, TXT, MD…)');
          continue;
        }
        if (file.size > maxBytes) {
          setAttachError(
            `Archivo demasiado grande (máx. ${Math.round(maxBytes / (1024 * 1024))} MB)`
          );
          continue;
        }
        try {
          const data_base64 = await fileToBase64(file);
          next.push({
            id: `${Date.now()}-${i}-${file.name}`,
            name: file.name,
            mime_type: guessChatDocumentMime(file),
            data_base64,
            size: file.size,
          });
        } catch (e) {
          setAttachError(e instanceof Error ? e.message : 'Error al leer archivo');
        }
      }
      setPending(next);
      if (fileInputRef.current) fileInputRef.current.value = '';
    },
    [maxBytes, maxCount, pending]
  );

  const buildPayloadDocuments = useCallback(
    (): ChatDocumentPayload[] =>
      pending.map((p) => ({
        filename: p.name,
        mime_type: p.mime_type,
        data_base64: p.data_base64,
      })),
    [pending]
  );

  return {
    pendingDocuments: pending,
    attachError,
    setAttachError,
    fileInputRef,
    onPickFiles: ingestFiles,
    ingestFiles,
    removeDocument,
    clearDocuments,
    buildPayloadDocuments,
    hasDocuments: pending.length > 0,
  };
}
