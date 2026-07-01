'use client';

import { PageShell } from '@/components/admin/PageShell';
import { cn } from '@/lib/utils';

export type AdminHubTab = {
  id: string;
  label: string;
  hint?: string;
};

type AdminHubShellProps = {
  title: string;
  description: string;
  tabs: readonly AdminHubTab[];
  activeTabId: string;
  onSelectTab: (tabId: string) => void;
  children: React.ReactNode;
};

export function AdminHubShell({
  title,
  description,
  tabs,
  activeTabId,
  onSelectTab,
  children,
}: AdminHubShellProps) {
  const activeTab = tabs.find((tab) => tab.id === activeTabId);

  return (
    <PageShell className="space-y-6">
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">{title}</h1>
        <p className="mt-1 max-w-3xl text-sm text-gov-gray-500 dark:text-dark-muted">{description}</p>
      </header>

      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
        {tabs.map((tab) => {
          const selected = tab.id === activeTabId;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => onSelectTab(tab.id)}
              className={cn(
                'rounded-xl px-4 py-3 text-left sm:min-w-[140px]',
                selected
                  ? 'bg-gov-blue-700 text-white'
                  : 'border border-gov-blue-200 text-gov-blue-800 dark:border-dark-border dark:text-dark-cyan'
              )}
            >
              <span className="block text-sm font-black">{tab.label}</span>
              {tab.hint ? (
                <span
                  className={cn(
                    'mt-0.5 block text-xs font-normal',
                    selected ? 'text-blue-100' : 'text-gov-gray-500 dark:text-dark-muted'
                  )}
                >
                  {tab.hint}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      <div>{children}</div>
    </PageShell>
  );
}
