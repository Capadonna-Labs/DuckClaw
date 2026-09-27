'use client';

import Link from 'next/link';
import { ChevronRight } from 'lucide-react';
import { ChatLlmSelectors } from '@/components/chat/ChatLlmSelectors';
import { ChatSlmSelector } from '@/components/chat/ChatSlmSelector';
import { ConversationVaultSelector } from '@/components/chat/ConversationVaultSelector';
import { MarkdownSnippetPanel } from '@/components/chat/MarkdownSnippetPanel';
import { workerOptionIds } from '@/lib/workerOptions';
import type { KnowledgeScope } from '@/lib/knowledgeScope';
import {
  ChatCommandsPanel,
  ProjectAgentControls,
  SettingsModal,
} from '@/components/playground/PlaygroundSettingsParts';
import type {
  PlaygroundConfig,
  PlaygroundSettingsModal,
} from '@/components/playground/playgroundTypes';

export function PlaygroundSettingsDialogs({
  settingsModal,
  onClose,
  config,
  projectId,
  knowledgeScope,
  activeProject,
  projectWorkerIds,
  selectableWorkers,
  workerId,
  onProjectIdChange,
  onSelectWorker,
  onKnowledgeScopeChange,
  sessionId,
  profileTenantId,
  chatLoading,
  vaultPath,
  onVaultPathChange,
  activeVaultPath,
  activeVaultScope,
  systemPreview,
  onConfigUpdated,
}: {
  settingsModal: PlaygroundSettingsModal;
  onClose: () => void;
  config: PlaygroundConfig | null;
  projectId: string;
  knowledgeScope: KnowledgeScope;
  activeProject?: NonNullable<PlaygroundConfig['projects']>[number];
  projectWorkerIds: string[];
  selectableWorkers: NonNullable<PlaygroundConfig['workers']>;
  workerId: string;
  onProjectIdChange: (projectId: string) => void;
  onSelectWorker: (workerId: string) => void;
  onKnowledgeScopeChange: (scope: KnowledgeScope) => void;
  sessionId: string | null | undefined;
  profileTenantId: string;
  chatLoading: boolean;
  vaultPath: string;
  onVaultPathChange: (path: string) => void;
  activeVaultPath: string;
  activeVaultScope: string | undefined;
  systemPreview: string;
  onConfigUpdated: () => void;
}) {
  if (!settingsModal) return null;

  return (
    <>
      {settingsModal === 'routing' && (
        <SettingsModal
          title="Contexto del chat"
          description="Proyecto, agente y alcance de conocimiento RAG."
          onClose={onClose}
        >
          <ProjectAgentControls
            config={config}
            projectId={projectId}
            knowledgeScope={knowledgeScope}
            activeProject={activeProject}
            projectWorkerIds={projectWorkerIds}
            selectableWorkers={selectableWorkers}
            workerId={workerId}
            onProjectChange={(nextProjectId) => {
              onProjectIdChange(nextProjectId);
              const nextProject = (config?.projects ?? []).find(
                (project) => project.project_id === nextProjectId
              );
              const nextProjectWorkers =
                nextProject?.agents.map((agent) => agent.worker_id).filter(Boolean) ?? [];
              if (nextProjectWorkers.length > 0) {
                const keepCurrent =
                  workerId.trim() && nextProjectWorkers.includes(workerId.trim());
                onSelectWorker(keepCurrent ? workerId : nextProjectWorkers[0]!);
                return;
              }
              // Sin agentes en el proyecto: no vaciar — loadConfig / lista global mantiene default.
              if (!workerId.trim()) {
                const ids = workerOptionIds(config?.workers);
                const fallback = ids.includes('default') ? 'default' : ids[0] ?? '';
                if (fallback) onSelectWorker(fallback);
              }
            }}
            onWorkerChange={onSelectWorker}
            onKnowledgeScopeChange={onKnowledgeScopeChange}
          />
        </SettingsModal>
      )}

      {settingsModal === 'model' && (
        <SettingsModal
          title="Model selection"
          description="Proveedor LLM (nube o inferencia local). SLM abajo es herramienta aparte."
          size="wide"
          onClose={onClose}
        >
          {sessionId ? (
            <div className="space-y-6">
              <div className="space-y-3">
                <p className="text-xs font-black uppercase tracking-wider text-gov-gray-500">LLM</p>
                <ChatLlmSelectors
                  chatId={sessionId}
                  tenantId={config?.effective_tenant_id || profileTenantId}
                  provider={config?.llm?.provider ?? ''}
                  model={config?.llm?.model ?? ''}
                  catalog={config?.catalog ?? []}
                  mlxInference={config?.slm}
                  onUpdated={onConfigUpdated}
                  disabled={config?.authorized === false || chatLoading}
                  size="modal"
                />
              </div>
              <div className="space-y-3 border-t dark:border-dark-border pt-4">
                <p className="text-xs font-black uppercase tracking-wider text-gov-gray-500">
                  SLM
                </p>
                <ChatSlmSelector
                  chatId={sessionId}
                  slm={config?.slm}
                  onUpdated={onConfigUpdated}
                  disabled={config?.authorized === false || chatLoading}
                  size="modal"
                />
              </div>
            </div>
          ) : (
            <p className="text-xs text-gov-gray-500">Cargando conversación…</p>
          )}
        </SettingsModal>
      )}

      {settingsModal === 'vault' && (
        <SettingsModal
          title="Base de datos de esta sesión"
          description="Archivo .duckdb que usa esta conversación para SQL, reglas y conocimiento (RAG)."
          onClose={onClose}
        >
          {sessionId ? (
            <ConversationVaultSelector
              chatId={sessionId}
              tenantId={config?.effective_tenant_id}
              value={vaultPath}
              effectivePath={activeVaultPath}
              scope={activeVaultScope}
              options={config?.vault_options}
              onChange={onVaultPathChange}
              onUpdated={onConfigUpdated}
              compact
            />
          ) : (
            <p className="text-xs text-gov-gray-500">Cargando conversación…</p>
          )}
        </SettingsModal>
      )}

      {settingsModal === 'instructions' && (
        <SettingsModal
          title="System instructions"
          description="Prompt base del agente seleccionado."
          onClose={onClose}
        >
          <MarkdownSnippetPanel
            content={systemPreview}
            emptyLabel="Sin system_prompt.md"
            maxHeightClass="max-h-72"
          />
          <Link
            href={`/templates/${workerId}?focus=system_prompt.md`}
            className="text-xs text-gov-blue-700 font-semibold mt-3 inline-flex items-center gap-1"
          >
            Editar comportamiento <ChevronRight size={12} />
          </Link>
        </SettingsModal>
      )}

      {settingsModal === 'commands' && (
        <SettingsModal
          title="Comandos"
          description="Atajos copiables para hablar con el agente."
          onClose={onClose}
        >
          <ChatCommandsPanel />
        </SettingsModal>
      )}
    </>
  );
}
