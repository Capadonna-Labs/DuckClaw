'use client';

import { useState } from 'react';

/**
 * Root error boundary (Next.js App Router convention): catches whatever escapes
 * every other boundary. Without this file, a client-side exception falls through
 * to Next's generic "Application error" blank page with the real message only in
 * a browser console nobody on an iOS PWA can reach without a Mac + Safari Web
 * Inspector — which is exactly why three fix attempts tonight went in blind.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const details = `${error.message}\n\n${error.stack || ''}${
    error.digest ? `\n\ndigest: ${error.digest}` : ''
  }`;

  return (
    <html lang="es">
      <body
        style={{
          margin: 0,
          padding: '24px',
          fontFamily: 'system-ui, -apple-system, sans-serif',
          background: '#161B22',
          color: '#e2e8f0',
        }}
      >
        <h1 style={{ fontSize: '1.1rem', marginBottom: '8px' }}>
          Algo falló en DuckClaw Admin
        </h1>
        <pre
          style={{
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            background: '#0d1117',
            border: '1px solid #30363d',
            borderRadius: '8px',
            padding: '12px',
            fontSize: '0.8rem',
            maxHeight: '50vh',
            overflow: 'auto',
          }}
        >
          {details}
        </pre>
        <div style={{ display: 'flex', gap: '8px', marginTop: '16px' }}>
          <button
            type="button"
            onClick={() => reset()}
            style={{
              padding: '10px 16px',
              borderRadius: '8px',
              border: 'none',
              background: '#2563eb',
              color: '#fff',
              fontSize: '0.9rem',
            }}
          >
            Reintentar
          </button>
          <button
            type="button"
            onClick={() => {
              navigator.clipboard?.writeText(details).then(() => setCopied(true));
            }}
            style={{
              padding: '10px 16px',
              borderRadius: '8px',
              border: '1px solid #30363d',
              background: 'transparent',
              color: '#e2e8f0',
              fontSize: '0.9rem',
            }}
          >
            {copied ? 'Copiado ✓' : 'Copiar error'}
          </button>
        </div>
      </body>
    </html>
  );
}
