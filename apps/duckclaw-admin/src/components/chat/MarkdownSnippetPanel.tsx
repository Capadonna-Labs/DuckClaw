'use client';

import { useState, type ReactNode } from 'react';
import { Eye, FileCode } from 'lucide-react';
import { ChatMarkdown } from '@/components/chat/ChatMarkdown';

type ViewMode = 'raw' | 'preview';

type Props = {
  content: string;
  emptyLabel?: string;
  maxHeightClass?: string;
};

export function MarkdownSnippetPanel({
  content,
  emptyLabel = 'Sin contenido',
  maxHeightClass = 'max-h-48',
}: Props) {
  const [mode, setMode] = useState<ViewMode>('raw');
  const text = (content || '').trim();

  return (
    <div className="space-y-2">
      <div
        className="flex gap-1"
        role="tablist"
        aria-label="Vista de instrucciones"
      >
        <ViewButton
          active={mode === 'raw'}
          onClick={() => setMode('raw')}
          icon={<FileCode size={12} />}
          label="Markdown"
        />
        <ViewButton
          active={mode === 'preview'}
          onClick={() => setMode('preview')}
          icon={<Eye size={12} />}
          label="Vista previa"
        />
      </div>

      {!text ? (
        <p className="text-xs text-gov-gray-400 italic">{emptyLabel}</p>
      ) : mode === 'raw' ? (
        <pre
          className={`text-[10px] font-mono whitespace-pre-wrap overflow-y-auto text-gov-gray-600 dark:text-dark-muted rounded-xl border dark:border-dark-border bg-gov-gray-50 dark:bg-dark-bg p-3 ${maxHeightClass}`}
        >
          {content}
        </pre>
      ) : (
        <div
          className={`overflow-y-auto rounded-xl border dark:border-dark-border bg-gov-gray-50 dark:bg-dark-bg p-3 ${maxHeightClass}`}
        >
          <ChatMarkdown content={content} className="text-xs prose-sm" />
        </div>
      )}
    </div>
  );
}

function ViewButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-bold border transition-colors ${
        active
          ? 'bg-gov-blue-700 text-white border-gov-blue-700'
          : 'border-transparent bg-gov-gray-100 dark:bg-dark-bg text-gov-gray-600 dark:text-dark-muted hover:border-gov-gray-300 dark:hover:border-dark-border'
      }`}
    >
      {icon}
      {label}
    </button>
  );
}
