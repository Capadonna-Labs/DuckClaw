'use client';

import { useCallback, useRef, useState } from 'react';

export const CHAT_IMAGE_MIME = new Set(['image/jpeg', 'image/png', 'image/webp']);
const ALLOWED_MIME = CHAT_IMAGE_MIME;

export function imageFilesFromClipboardData(data: DataTransfer | null): File[] {
  if (!data) return [];
  const files: File[] = [];
  const seen = new Set<string>();

  const maybeAdd = (file: File | null) => {
    if (!file) return;
    const mime = (file.type || '').toLowerCase();
    if (!ALLOWED_MIME.has(mime)) return;
    const key = `${file.name}:${file.size}:${mime}`;
    if (seen.has(key)) return;
    seen.add(key);
    files.push(file);
  };

  if (data.items?.length) {
    for (let i = 0; i < data.items.length; i += 1) {
      const item = data.items[i];
      if (item.kind !== 'file') continue;
      maybeAdd(item.getAsFile());
    }
  }

  for (const file of Array.from(data.files ?? [])) {
    maybeAdd(file);
  }

  return files;
}

export function nonImageFilesFromClipboardData(data: DataTransfer | null): File[] {
  if (!data) return [];
  const files: File[] = [];
  const seen = new Set<string>();

  const maybeAdd = (file: File | null) => {
    if (!file) return;
    const mime = (file.type || '').toLowerCase();
    if (ALLOWED_MIME.has(mime)) return;
    const key = `${file.name}:${file.size}:${mime || 'octet'}`;
    if (seen.has(key)) return;
    seen.add(key);
    files.push(file);
  };

  if (data.items?.length) {
    for (let i = 0; i < data.items.length; i += 1) {
      const item = data.items[i];
      if (item.kind !== 'file') continue;
      maybeAdd(item.getAsFile());
    }
  }

  for (const file of Array.from(data.files ?? [])) {
    maybeAdd(file);
  }

  return files;
}
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

  const ingestFiles = useCallback(
    async (files: FileList | readonly File[] | null) => {
      const fileList = files
        ? files instanceof FileList
          ? Array.from(files)
          : [...files]
        : [];
      if (fileList.length === 0) return;
      setAttachError(null);
      const next: PendingChatImage[] = [...pending];
      for (let i = 0; i < fileList.length; i += 1) {
        if (next.length >= maxCount) {
          setAttachError(`Máximo ${maxCount} imágenes por mensaje`);
          break;
        }
        const file = fileList[i];
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

  const onPickFiles = ingestFiles;

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
    setAttachError,
    fileInputRef,
    onPickFiles,
    ingestFiles,
    removeImage,
    clearImages,
    buildPayloadImages,
    buildUserPreviews,
    hasImages: pending.length > 0,
  };
}
