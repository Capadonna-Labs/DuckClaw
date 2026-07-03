'use client';

import { Database } from 'lucide-react';
import {
  KNOWLEDGE_SCOPE_OPTIONS,
  normalizeKnowledgeScope,
  type KnowledgeScope,
} from '@/lib/knowledgeScope';

type Props = {
  value: KnowledgeScope;
  projectId: string;
  disabled?: boolean;
  compact?: boolean;
  onChange: (scope: KnowledgeScope) => void;
};

export function KnowledgeScopeControl({
  value,
  projectId,
  disabled = false,
  compact = false,
  onChange,
}: Props) {
  const normalized = normalizeKnowledgeScope(value, projectId);
  const activeOption = KNOWLEDGE_SCOPE_OPTIONS.find((o) => o.id === normalized);

  return (
    <div className={compact ? 'space-y-2' : 'space-y-3'}>
      {!compact && (
        <div className="flex items-center gap-2">
          <Database size={16} className="text-gov-blue-600 dark:text-dark-cyan" aria-hidden />
          <div>
            <p className="text-xs font-bold text-gov-gray-800 dark:text-dark-text">Conocimiento RAG</p>
            <p className="text-[10px] text-gov-gray-500 dark:text-dark-muted">
              Qué documentos puede consultar el agente en este chat.
            </p>
          </div>
        </div>
      )}
      <div
        className="grid grid-cols-3 gap-1 rounded-xl border border-gov-gray-200 bg-gov-gray-50 p-1 dark:border-dark-border dark:bg-dark-bg"
        role="radiogroup"
        aria-label="Alcance de conocimiento RAG"
      >
        {KNOWLEDGE_SCOPE_OPTIONS.map((option) => {
          const blocked = Boolean(option.requiresProject && !projectId.trim());
          const selected = normalized === option.id;
          return (
            <button
              key={option.id}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={disabled || blocked}
              title={blocked ? 'Elige un proyecto primero' : option.hint}
              onClick={() => onChange(option.id)}
              className={`rounded-lg px-2 py-2 text-center transition-colors ${
                selected
                  ? 'bg-white text-gov-blue-800 shadow-sm dark:bg-dark-surface dark:text-dark-cyan'
                  : 'text-gov-gray-600 hover:bg-white/70 dark:text-dark-muted dark:hover:bg-dark-surface/60'
              } disabled:cursor-not-allowed disabled:opacity-40`}
            >
              <span className="block text-[11px] font-bold">{option.label}</span>
            </button>
          );
        })}
      </div>
      {activeOption && (
        <p className="text-[10px] leading-relaxed text-gov-gray-500 dark:text-dark-muted">{activeOption.hint}</p>
      )}
    </div>
  );
}
