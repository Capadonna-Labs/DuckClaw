'use client';

import type { WorkerRoleTemplate, WorkerRoleTemplateId } from '@/lib/workerRoleTemplates';
import { WORKER_ROLE_TEMPLATES } from '@/lib/workerRoleTemplates';

type WorkerRoleTemplatePickerProps = {
  selectedId: WorkerRoleTemplateId;
  onSelect: (role: WorkerRoleTemplate) => void;
  disabled?: boolean;
};

export function WorkerRoleTemplatePicker({ selectedId, onSelect, disabled }: WorkerRoleTemplatePickerProps) {
  return (
    <fieldset className="space-y-2" disabled={disabled}>
      <legend className="text-xs font-medium text-gov-gray-700 dark:text-dark-text">Tipo de agente</legend>
      <div className="grid gap-2 sm:grid-cols-2">
        {WORKER_ROLE_TEMPLATES.map((role) => {
          const selected = selectedId === role.id;
          return (
            <label
              key={role.id}
              className={`flex cursor-pointer gap-2 rounded-lg border px-3 py-2 ${
                selected
                  ? 'border-gov-blue-600 bg-gov-blue-50 dark:border-dark-cyan dark:bg-dark-bg'
                  : 'border-gov-gray-200 dark:border-dark-border'
              }`}
            >
              <input
                type="radio"
                name="worker-role-template"
                className="mt-1"
                checked={selected}
                disabled={disabled}
                onChange={() => onSelect(role)}
              />
              <span>
                <span className="block text-xs font-semibold text-gov-gray-900 dark:text-dark-text">
                  {role.title}
                </span>
                <span className="mt-0.5 block text-[10px] leading-snug text-gov-gray-500 dark:text-dark-muted">
                  {role.description}
                </span>
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
