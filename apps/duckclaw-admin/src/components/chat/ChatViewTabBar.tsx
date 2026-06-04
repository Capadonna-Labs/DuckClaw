'use client';

export type ChatViewTab = 'chat' | 'conversation';

type Props = {
  active: ChatViewTab;
  onChange: (tab: ChatViewTab) => void;
  className?: string;
};

export function ChatViewTabBar({ active, onChange, className = '' }: Props) {
  const tabCls = (on: boolean) =>
    `flex-1 min-h-[44px] px-3 py-2 text-xs font-bold rounded-xl transition-colors ${
      on
        ? 'bg-gov-blue-700 text-white shadow-sm'
        : 'text-gov-gray-600 dark:text-dark-muted hover:bg-gov-gray-100 dark:hover:bg-dark-bg border border-transparent dark:hover:border-dark-border'
    }`;

  return (
    <div
      className={`flex gap-2 p-2 border-b dark:border-dark-border bg-gov-gray-50/80 dark:bg-dark-bg/80 shrink-0 ${className}`}
      role="tablist"
      aria-label="Vista del asistente"
    >
      <button
        type="button"
        role="tab"
        aria-selected={active === 'chat'}
        className={tabCls(active === 'chat')}
        onClick={() => onChange('chat')}
      >
        Chat
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={active === 'conversation'}
        className={tabCls(active === 'conversation')}
        onClick={() => onChange('conversation')}
      >
        Conversación
      </button>
    </div>
  );
}
