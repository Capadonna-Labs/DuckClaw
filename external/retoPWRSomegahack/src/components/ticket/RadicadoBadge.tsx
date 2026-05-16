'use client';

import { useState } from 'react';
import { Copy, Check } from 'lucide-react';
import { formatearRadicadoCorto } from '@/lib/radicado';

interface RadicadoBadgeProps {
  numeroRadicado: string;
  variant?:  'full' | 'short';   // default: 'full'
  copyable?: boolean;             // default: false
  size?:     'sm' | 'md' | 'lg'; // default: 'md'
}

export default function RadicadoBadge({
  numeroRadicado,
  variant  = 'full',
  copyable = false,
  size     = 'md',
}: RadicadoBadgeProps) {

  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(numeroRadicado);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback para navegadores sin API Clipboard
      console.warn('Clipboard API no disponible');
    }
  }

  // VARIANTE COMPACTA (para tablas)
  if (variant === 'short') {
    return (
      <span
        title={`Radicado: ${numeroRadicado}`}
        className="inline-block font-mono text-xs px-2 py-0.5 rounded
          bg-gov-blue-100 text-gov-blue-700 border border-gov-blue-200
          dark:bg-dark-surface dark:text-dark-cyan dark:border-dark-border"
      >
        {formatearRadicadoCorto(numeroRadicado)}
      </span>
    );
  }

  // VARIANTE COMPLETA (para vista de detalle)
  const textSizeClass = {
    sm: 'text-xs',
    md: 'text-sm',
    lg: 'text-base',
  }[size];

  return (
    <div
      role="text"
      title={`Número de radicado oficial: ${numeroRadicado}`}
      className="inline-flex items-center gap-2 bg-gov-blue-900 dark:bg-dark-sidebar
        text-white px-3 py-1.5 rounded-lg"
    >
      {/* Label lateral */}
      <span className="text-[9px] text-gov-cyan-400 font-bold tracking-widest
        uppercase leading-none">
        RAD
      </span>

      {/* Número principal */}
      <span className={`font-mono font-bold tracking-wide text-gov-cyan-400 ${textSizeClass}`}>
        {numeroRadicado}
      </span>

      {/* Botón de copia */}
      {copyable && (
        <button
          onClick={handleCopy}
          aria-label="Copiar número de radicado"
          className="text-gov-gray-400 hover:text-gov-cyan-400
            transition-colors ml-0.5 flex-shrink-0"
        >
          {copied
            ? <Check size={14} className="text-[#00875A]" />
            : <Copy size={14} />
          }
        </button>
      )}
    </div>
  );
}
