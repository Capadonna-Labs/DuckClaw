'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';

/** Separa sufijo «(worker: …)» añadido por el playground tras el streaming. */
export function splitPlaygroundWorkerSuffix(text: string): { body: string; workerNote: string | null } {
  const m = text.match(/^([\s\S]*)(\s*\(worker:\s*[^)]+\))\s*$/);
  if (!m) return { body: text, workerNote: null };
  return { body: m[1].trimEnd(), workerNote: m[2].trim() };
}

const markdownComponents: Components = {
  p: ({ children }) => <p className="mb-3 last:mb-0 leading-relaxed">{children}</p>,
  h1: ({ children }) => (
    <h1 className="text-base font-black mb-2 mt-4 first:mt-0 text-gov-gray-900 dark:text-dark-text">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-sm font-bold mb-2 mt-3 first:mt-0 text-gov-gray-900 dark:text-dark-text">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-sm font-semibold mb-1.5 mt-2 first:mt-0 text-gov-gray-800 dark:text-dark-text">
      {children}
    </h3>
  ),
  ul: ({ children }) => <ul className="list-disc pl-5 mb-3 space-y-1.5 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5 mb-3 space-y-1.5 last:mb-0">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="border-l-4 border-gov-blue-400 dark:border-dark-cyan pl-3 my-3 text-gov-gray-600 dark:text-dark-muted italic">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-4 border-gov-gray-200 dark:border-dark-border" />,
  strong: ({ children }) => <strong className="font-bold text-gov-gray-900 dark:text-dark-text">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-gov-blue-700 dark:text-dark-cyan underline underline-offset-2 hover:text-gov-blue-500 break-all"
    >
      {children}
    </a>
  ),
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded-xl border border-gov-gray-200 dark:border-dark-border">
      <table className="w-full min-w-[240px] text-xs border-collapse">{children}</table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-gov-gray-100 dark:bg-dark-sidebar text-left">{children}</thead>
  ),
  th: ({ children }) => (
    <th className="px-3 py-2 font-bold border-b border-gov-gray-200 dark:border-dark-border">{children}</th>
  ),
  td: ({ children }) => (
    <td className="px-3 py-2 border-b border-gov-gray-100 dark:border-dark-border align-top">{children}</td>
  ),
  pre: ({ children }) => (
    <pre className="my-3 overflow-x-auto rounded-xl bg-gov-gray-900 dark:bg-[#010409] text-gov-gray-50 p-3 text-xs leading-relaxed font-mono">
      {children}
    </pre>
  ),
  code: ({ className, children, ...props }) => {
    const isBlock = Boolean(className?.includes('language-'));
    if (isBlock) {
      return (
        <code className={`${className ?? ''} font-mono text-inherit`} {...props}>
          {children}
        </code>
      );
    }
    return (
      <code
        className="px-1.5 py-0.5 rounded-md bg-gov-gray-200/90 dark:bg-dark-border text-[0.85em] font-mono text-gov-blue-900 dark:text-dark-cyan"
        {...props}
      >
        {children}
      </code>
    );
  },
};

type ChatMarkdownProps = {
  content: string;
  className?: string;
};

/**
 * Renderiza Markdown (GFM: tablas, listas, código, enlaces) para burbujas del asistente.
 * Seguro por defecto: sin HTML crudo (react-markdown).
 */
export function ChatMarkdown({ content, className = '' }: ChatMarkdownProps) {
  const { body, workerNote } = splitPlaygroundWorkerSuffix(content);

  if (!body.trim() && !workerNote) {
    return null;
  }

  return (
    <div className={`chat-markdown max-w-none break-words ${className}`}>
      {body.trim() ? (
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
          {body}
        </ReactMarkdown>
      ) : null}
      {workerNote && (
        <p className="mt-2 text-[10px] text-gov-gray-500 dark:text-dark-muted font-mono">{workerNote}</p>
      )}
    </div>
  );
}
