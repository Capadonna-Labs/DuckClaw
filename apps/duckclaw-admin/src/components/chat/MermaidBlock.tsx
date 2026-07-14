'use client';

import { useEffect, useId, useState } from 'react';

type MermaidBlockProps = {
  source: string;
  variant?: 'assistant' | 'user';
};

export function MermaidBlock({ source, variant = 'assistant' }: MermaidBlockProps) {
  const reactId = useId().replace(/:/g, '');
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const diagram = (source || '').trim();
  const fallbackPre =
    variant === 'user'
      ? 'my-3 overflow-x-auto rounded-xl bg-black/25 text-white p-3 text-xs font-mono'
      : 'my-3 overflow-x-auto rounded-xl bg-gov-gray-900 dark:bg-[#010409] text-gov-gray-50 p-3 text-xs font-mono';

  useEffect(() => {
    if (!diagram) return undefined;
    let cancelled = false;

    void (async () => {
      try {
        const { default: mermaid } = await import('mermaid');
        const prefersDark =
          typeof document !== 'undefined' &&
          document.documentElement.classList.contains('dark');
        mermaid.initialize({
          startOnLoad: false,
          theme: prefersDark ? 'dark' : 'neutral',
          securityLevel: 'strict',
          fontFamily: 'inherit',
        });
        const renderId = `duckclaw-mermaid-${reactId}`;
        const { svg: rendered } = await mermaid.render(renderId, diagram);
        if (!cancelled) {
          setSvg(rendered);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setSvg(null);
          setError(err instanceof Error ? err.message : 'Diagrama Mermaid inválido');
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [diagram, reactId]);

  if (!diagram) return null;

  if (error) {
    return (
      <div className="my-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-900/50 dark:bg-amber-950/30">
        <p className="text-[10px] font-semibold text-amber-900 dark:text-amber-100">
          No se pudo renderizar Mermaid
        </p>
        <pre className={`${fallbackPre} mt-2`}>{diagram}</pre>
      </div>
    );
  }

  if (!svg) {
    return (
      <div
        className="my-3 flex min-h-[4rem] items-center justify-center rounded-xl border border-gov-gray-200 bg-gov-gray-50 text-[11px] text-gov-gray-500 dark:border-dark-border dark:bg-dark-bg dark:text-dark-muted"
        aria-busy="true"
      >
        Renderizando diagrama…
      </div>
    );
  }

  return (
    <div
      className="mermaid-diagram my-3 max-w-full overflow-x-auto rounded-xl border border-gov-gray-200 bg-white p-3 dark:border-dark-border dark:bg-dark-surface [&_svg]:mx-auto [&_svg]:max-w-full"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
