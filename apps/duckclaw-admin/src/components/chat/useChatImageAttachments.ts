'use client';

import { useCallback, useRef, useState } from 'react';

const ALLOWED_MIME = new Set(['image/jpeg', 'image/png', 'image/webp']);
const DEFAULT_MAX_BYTES = 12 * 1024 * 1024;

export type PendingChatImage = {
  id: string;
  name: string;
  previewUrl: string;
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
    reader.onerror = () => reject(new Error('No se pudo leer la imagen'));
    reader.readAsDataURL(file);
  });
}

export function useChatImageAttachments(maxCount = 3, maxBytes = DEFAULT_MAX_BYTES) {
  const [pending, setPending] = useState<PendingChatImage[]>([]);
  const [attachError, setAttachError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const revokeAll = useCallback((items: PendingChatImage[]) => {
    for (const p of items) {
      try {
        URL.revokeObjectURL(p.previewUrl);
      } catch {
        /* ignore */
      }
    }
  }, []);

  const clearImages = useCallback(
    (options?: { revoke?: boolean }) => {
      const shouldRevoke = options?.revoke !== false;
      setPending((prev) => {
        if (shouldRevoke) revokeAll(prev);
        return [];
      });
      setAttachError(null);
    },
    [revokeAll]
  );

  const removeImage = useCallback(
    (id: string) => {
      setPending((prev) => {
        const target = prev.find((p) => p.id === id);
        if (target) {
          try {
            URL.revokeObjectURL(target.previewUrl);
          } catch {
            /* ignore */
          }
        }
        return prev.filter((p) => p.id !== id);
      });
    },
    []
  );

  const onPickFiles = useCallback(
    async (files: FileList | null) => {
      if (!files?.length) return;
      setAttachError(null);
      const next: PendingChatImage[] = [...pending];
      for (let i = 0; i < files.length; i += 1) {
        if (next.length >= maxCount) {
          setAttachError(`Máximo ${maxCount} imágenes por mensaje`);
          break;
        }
        const file = files[i];
        const mime = (file.type || '').toLowerCase();
        if (!ALLOWED_MIME.has(mime)) {
          setAttachError('Solo JPEG, PNG o WebP');
          continue;
        }
        if (file.size > maxBytes) {
          setAttachError(`Imagen demasiado grande (máx. ${Math.round(maxBytes / (1024 * 1024))} MB)`);
          continue;
        }
        try {
          const data_base64 = await fileToBase64(file);
          next.push({
            id: `${Date.now()}-${i}-${file.name}`,
            name: file.name,
            previewUrl: URL.createObjectURL(file),
            mime_type: mime,
            data_base64,
          });
        } catch (e) {
          setAttachError(e instanceof Error ? e.message : 'Error al leer imagen');
        }
      }
      setPending(next);
      if (fileInputRef.current) fileInputRef.current.value = '';
    },
    [maxBytes, maxCount, pending]
  );

  const buildPayloadImages = useCallback(
    () =>
      pending.map((p) => ({
        mime_type: p.mime_type,
        data_base64: p.data_base64,
      })),
    [pending]
  );

  const buildUserPreviews = useCallback(
    () => pending.map((p) => ({ url: p.previewUrl, name: p.name })),
    [pending]
  );

  return {
    pendingImages: pending,
    attachError,
    fileInputRef,
    onPickFiles,
    removeImage,
    clearImages,
    buildPayloadImages,
    buildUserPreviews,
    hasImages: pending.length > 0,
  };
}
