'use client';

import { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Download, X } from 'lucide-react';
import type { ChatImagePreview } from '@/components/chat/types';

type ArtifactImageLightboxProps = {
  image: ChatImagePreview | null;
  onClose: () => void;
};

/**
 * Vista ampliada de imagen en portal a document.body.
 * No montar dentro de burbujas/paneles con overflow-hidden: en iOS Safari
 * `position:fixed` hereda el clipping del ancestro y oculta título/Descargar/Cerrar.
 */
export function ArtifactImageLightbox({ image, onClose }: ArtifactImageLightboxProps) {
  const [mounted, setMounted] = useState(false);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    },
    [onClose]
  );

  useEffect(() => {
    setMounted(true);
  }, []);

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

  if (!image || !mounted) return null;

  const title =
    image.name?.trim() ||
    (image.artifactId ? `${image.artifactId}.png` : 'Imagen');
  const downloadName =
    image.name?.trim() && /\.(png|jpe?g|webp|gif)$/i.test(image.name)
      ? image.name.trim()
      : `${image.artifactId || 'imagen'}.png`;

  return createPortal(
    <div
      className="fixed inset-0 z-[300] flex flex-col bg-slate-950/90 backdrop-blur-sm"
      style={{
        paddingTop: 'env(safe-area-inset-top)',
        paddingBottom: 'env(safe-area-inset-bottom)',
      }}
      data-artifact-image-lightbox="true"
      role="dialog"
      aria-modal="true"
      aria-label="Vista ampliada de imagen"
    >
      <button
        type="button"
        className="absolute inset-0 cursor-default"
        aria-label="Cerrar vista ampliada"
        onClick={onClose}
      />
      <header className="relative z-[1] flex shrink-0 items-center gap-2 border-b border-white/10 bg-black/40 px-3 py-2.5 sm:px-4">
        <p
          className="min-w-0 flex-1 truncate text-sm font-semibold text-white"
          title={title}
        >
          {title}
        </p>
        <a
          href={image.url}
          download={downloadName}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-gov-blue-700 px-3 py-2 text-sm font-semibold text-white hover:bg-gov-blue-800"
          onClick={(e) => e.stopPropagation()}
        >
          <Download size={16} aria-hidden />
          <span className="hidden sm:inline">Descargar</span>
        </a>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex shrink-0 items-center justify-center rounded-xl border border-white/20 bg-white/10 p-2 text-white hover:bg-white/20"
          aria-label="Cerrar"
        >
          <X size={18} aria-hidden />
        </button>
      </header>
      <div className="relative z-[1] flex min-h-0 flex-1 items-center justify-center p-3 sm:p-4 pointer-events-none">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={image.url}
          alt={title}
          className="pointer-events-auto max-h-full max-w-full object-contain"
          onClick={(e) => e.stopPropagation()}
        />
      </div>
    </div>,
    document.body
  );
}
