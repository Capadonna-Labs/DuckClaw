'use client';

import { useCallback, useEffect } from 'react';
import { Download, X } from 'lucide-react';
import type { ChatImagePreview } from '@/components/chat/types';

type ArtifactImageLightboxProps = {
  image: ChatImagePreview | null;
  onClose: () => void;
};

export function ArtifactImageLightbox({ image, onClose }: ArtifactImageLightboxProps) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    },
    [onClose]
  );

  useEffect(() => {
    if (!image) return;
    document.addEventListener('keydown', handleKeyDown);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = prev;
    };
  }, [image, handleKeyDown]);

  if (!image) return null;

  const downloadName =
    image.name?.trim() && /\.(png|jpe?g|webp)$/i.test(image.name)
      ? image.name.trim()
      : `${image.artifactId || 'imagen'}.png`;

  return (
    <>
      <button
        type="button"
        className="fixed inset-0 bg-slate-900/80 backdrop-blur-sm z-[200] cursor-default"
        aria-label="Cerrar vista ampliada"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Vista ampliada de imagen"
        className="fixed inset-0 z-[201] flex flex-col items-center justify-center p-4 pointer-events-none"
      >
        <div className="pointer-events-auto flex flex-col max-w-[min(96vw,1200px)] max-h-[92vh] w-full">
          <div className="flex items-center justify-end gap-2 mb-2">
            <a
              href={image.url}
              download={downloadName}
              className="inline-flex items-center gap-2 px-3 py-2 text-sm font-semibold rounded-xl bg-gov-blue-700 text-white hover:bg-gov-blue-800"
            >
              <Download size={16} aria-hidden />
              Descargar
            </a>
            <button
              type="button"
              onClick={onClose}
              className="inline-flex items-center justify-center p-2 rounded-xl border border-white/20 bg-white/10 text-white hover:bg-white/20"
              aria-label="Cerrar"
            >
              <X size={18} aria-hidden />
            </button>
          </div>
          <div className="flex-1 min-h-0 flex items-center justify-center rounded-2xl border border-white/15 bg-black/40 overflow-hidden">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={image.url}
              alt={image.name || 'Imagen generada'}
              className="max-w-full max-h-[calc(92vh-4rem)] object-contain"
            />
          </div>
          {image.name ? (
            <p className="mt-2 text-center text-xs text-white/70 font-mono truncate">{image.name}</p>
          ) : null}
        </div>
      </div>
    </>
  );
}
