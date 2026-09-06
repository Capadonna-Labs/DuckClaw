'use client';

type AdminChatSuggestionChipsProps = {
  suggestions: string[];
  onPick: (text: string) => void;
};

/** Chips de continuación sugerida por LLM, arriba del textarea (solo cuando el input está vacío). */
export function AdminChatSuggestionChips({ suggestions, onPick }: AdminChatSuggestionChipsProps) {
  if (suggestions.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {suggestions.map((s, i) => (
        <button
          key={`${i}:${s}`}
          type="button"
          onClick={() => onPick(s)}
          className="rounded-full border border-gov-gray-200 bg-white px-3 py-1.5 text-xs text-gov-gray-700 hover:bg-gov-gray-50 dark:border-dark-border dark:bg-dark-surface dark:text-dark-text dark:hover:bg-dark-bg"
        >
          {s}
        </button>
      ))}
    </div>
  );
}
