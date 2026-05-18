'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Pencil } from 'lucide-react';

export type EditableConversationTitleProps = {
  value: string;
  onSave: (title: string) => Promise<void>;
  active?: boolean;
  compact?: boolean;
  className?: string;
};

export function EditableConversationTitle({
  value,
  onSave,
  active = false,
  compact = false,
  className = '',
}: EditableConversationTitleProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!editing) setDraft(value);
  }, [value, editing]);

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing]);

  const cancel = useCallback(() => {
    setEditing(false);
    setDraft(value);
    setErr(null);
  }, [value]);

  const commit = useCallback(async () => {
    const next = draft.trim();
    if (!next) {
      cancel();
      return;
    }
    if (next === value.trim()) {
      setEditing(false);
      return;
    }
    setSaving(true);
    setErr(null);
    try {
      await onSave(next);
      setEditing(false);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'No se pudo guardar');
    } finally {
      setSaving(false);
    }
  }, [cancel, draft, onSave, value]);

  if (editing) {
    return (
      <div
        className={`min-w-0 flex-1 ${className}`}
        onClick={(e) => e.stopPropagation()}
        onPointerDown={(e) => e.stopPropagation()}
      >
        <input
          ref={inputRef}
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              void commit();
            }
            if (e.key === 'Escape') {
              e.preventDefault();
              cancel();
            }
          }}
          onBlur={() => void commit()}
          disabled={saving}
          className={`w-full font-semibold rounded px-1 py-0.5 border ${
            active
              ? 'bg-white/15 border-white/40 text-white placeholder:text-white/60'
              : 'dark:bg-dark-surface dark:border-dark-border dark:text-dark-text'
          } ${compact ? 'text-xs' : 'text-sm'}`}
          aria-label="Nombre de conversación"
        />
        {err ? <p className="text-[10px] text-red-400 mt-0.5">{err}</p> : null}
      </div>
    );
  }

  return (
    <div
      className={`flex items-center gap-0.5 min-w-0 flex-1 group/title ${className}`}
      onClick={(e) => e.stopPropagation()}
      onPointerDown={(e) => e.stopPropagation()}
    >
      <span
        className={`font-semibold line-clamp-1 min-w-0 ${active ? '' : 'dark:text-dark-text'} ${
          compact ? 'text-xs' : 'text-sm'
        }`}
        onDoubleClick={() => setEditing(true)}
        title="Doble clic para renombrar"
      >
        {value}
      </span>
      <button
        type="button"
        onClick={() => setEditing(true)}
        className={`shrink-0 p-0.5 rounded opacity-0 group-hover/title:opacity-100 group-hover:opacity-100 focus:opacity-100 ${
          active ? 'text-white/80 hover:text-white' : 'text-gov-gray-400 hover:text-gov-blue-700'
        }`}
        aria-label="Renombrar conversación"
      >
        <Pencil size={compact ? 12 : 14} />
      </button>
    </div>
  );
}
