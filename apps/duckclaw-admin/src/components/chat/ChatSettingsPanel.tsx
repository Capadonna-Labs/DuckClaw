'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { PlaygroundRunSettingsPanel } from '@/components/playground/PlaygroundRunSettingsPanel';
import { PlaygroundSettingsDialogs } from '@/components/playground/PlaygroundSettingsDialogs';
import type { PlaygroundSettingsModal } from '@/components/playground/playgroundTypes';
import type { AdminChatController } from '@/components/chat/useAdminChat';
import { notificationPermission } from '@/lib/chatNotifications';
import { knowledgeScopeLabel, type KnowledgeScope } from '@/lib/knowledgeScope';
import { workerOptionId, workerOptionLabel } from '@/lib/workerOptions';
import { adminService } from '@/services/adminService';
import { useAuthStore } from '@/store/authStore';

export type ChatSettingsPanelProps = {
  chatId: string;
  chat: AdminChatController;
  projectId: string;
  onProjectIdChange: (projectId: string) => void;
  knowledgeScope: KnowledgeScope;
  onKnowledgeScopeChange: (scope: KnowledgeScope) => void;
  toolUsageEnabled: boolean;
  onToolUsageToggle: () => void;
  suggestionsEnabled: boolean;
  onSuggestionsToggle: () => void;
  notificationsEnabled: boolean;
  onNotificationsToggle: () => void;
};

/**
 * Playground "Settings" (same panel + dialogs) bound to any chat controller,
 * e.g. the floating chat drawer. State lives in the chat controller / caller.
 */
export function ChatSettingsPanel({
  chatId,
  chat,
  projectId,
  onProjectIdChange,
  knowledgeScope,
  onKnowledgeScopeChange,
  toolUsageEnabled,
  onToolUsageToggle,
  suggestionsEnabled,
  onSuggestionsToggle,
  notificationsEnabled,
  onNotificationsToggle,
}: ChatSettingsPanelProps) {
  const { config, workerId, setWorkerId, vaultPath, setVaultPath, reloadConfig, loading } = chat;
  const profileTenantId = useAuthStore((s) => s.usuario?.profile?.tenant_id?.trim() || '');
  const [settingsModal, setSettingsModal] = useState<PlaygroundSettingsModal>(null);
  const [systemPreview, setSystemPreview] = useState('');

  const activeProject = useMemo(
    () => (config?.projects ?? []).find((project) => project.project_id === projectId),
    [config?.projects, projectId]
  );
  const projectWorkerIds = useMemo(
    () => activeProject?.agents.map((agent) => agent.worker_id).filter(Boolean) ?? [],
    [activeProject]
  );
  const selectableWorkers = useMemo(
    () =>
      activeProject && projectWorkerIds.length > 0
        ? (config?.workers ?? []).filter((worker) => projectWorkerIds.includes(workerOptionId(worker)))
        : (config?.workers ?? []),
    [activeProject, config?.workers, projectWorkerIds]
  );

  useEffect(() => {
    if (!workerId) return;
    let cancelled = false;
    adminService
      .getTemplate(workerId)
      .then((t) => {
        const sp = t.contents['system_prompt.md'];
        if (!cancelled) setSystemPreview(typeof sp === 'string' ? sp : '');
      })
      .catch(() => {
        if (!cancelled) setSystemPreview('');
      });
    return () => {
      cancelled = true;
    };
  }, [workerId]);

  const selectWorker = useCallback(
    (next: string) => {
      if (next.trim()) setWorkerId(next.trim(), { persist: true });
    },
    [setWorkerId]
  );

  const activeVaultPath = vaultPath || config?.vault?.effective_path || '';
  const activeVaultScope = vaultPath ? 'chat' : config?.vault?.scope;

  return (
    <>
      <PlaygroundRunSettingsPanel
        config={config}
        workerId={workerId}
        activeVaultPath={activeVaultPath}
        activeVaultScope={activeVaultScope}
        workerLabel={
          workerOptionLabel(
            selectableWorkers.find((worker) => workerOptionId(worker) === workerId) ?? workerId
          ) || workerId || '—'
        }
        projectLabel={activeProject?.name || 'Todos los agentes'}
        knowledgeScopeLabel={knowledgeScopeLabel(knowledgeScope)}
        systemPreview={systemPreview}
        systemReady={Boolean(systemPreview.trim())}
        invalidWorkers={config?.workers_invalid ?? []}
        logsPanelOpen={false}
        toolUsageEnabled={toolUsageEnabled}
        onToolUsageToggle={onToolUsageToggle}
        suggestionsEnabled={suggestionsEnabled}
        onSuggestionsToggle={onSuggestionsToggle}
        notificationsEnabled={notificationsEnabled}
        notificationPermission={notificationPermission()}
        onNotificationsToggle={onNotificationsToggle}
        chatId={chatId}
        tenantId={config?.effective_tenant_id}
        onOpen={setSettingsModal}
      />
      <PlaygroundSettingsDialogs
        settingsModal={settingsModal}
        onClose={() => setSettingsModal(null)}
        config={config}
        projectId={projectId}
        knowledgeScope={knowledgeScope}
        activeProject={activeProject}
        projectWorkerIds={projectWorkerIds}
        selectableWorkers={selectableWorkers}
        workerId={workerId}
        onProjectIdChange={onProjectIdChange}
        onSelectWorker={selectWorker}
        onKnowledgeScopeChange={onKnowledgeScopeChange}
        sessionId={chatId}
        profileTenantId={profileTenantId}
        chatLoading={loading}
        vaultPath={vaultPath}
        onVaultPathChange={setVaultPath}
        activeVaultPath={activeVaultPath}
        activeVaultScope={activeVaultScope}
        systemPreview={systemPreview}
        onConfigUpdated={reloadConfig}
      />
    </>
  );
}
