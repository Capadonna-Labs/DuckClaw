'use client';

import { useState } from 'react';
import {
  Brain,
  ChevronDown,
  ChevronRight,
  Cpu,
  FileText,
  Terminal,
} from 'lucide-react';

import { PlaygroundWorkerCapabilitiesPanel } from '@/components/playground/PlaygroundWorkerCapabilitiesPanel';
import { LlmSecretsBanner } from '@/components/integrations/LlmSecretsBanner';

type PlaygroundConfig = {
  llm?: { provider?: string; model?: string };
  llm_gap?: {
    provider: string;
    label: string;
    message: string;
    admin_href: string;
    integration_id?: string;
  } | null;
  slm?: {
    enabled?: boolean;
    model_short?: string;
    mlx_status?: string;
    pm2_name?: string;
  };
  workers_invalid?: string[];
} | null;

type SettingsModalKey = 'model' | 'vault' | 'routing' | 'instructions' | 'commands';

export type PlaygroundRunSettingsPanelProps = {
  config: PlaygroundConfig;
  workerId: string;
  capabilitiesRefreshKey?: number;
  activeVaultPath: string;
  activeVaultScope?: string;
  workerLabel: string;
  projectLabel: string;
  knowledgeScopeLabel: string;
  systemPreview: string;
  systemReady: boolean;
  invalidWorkers: string[];
  logsPanelOpen: boolean;
  onLogsToggle: () => void;
  logsControls?: React.ReactNode;
  logsViewport?: React.ReactNode;
  onOpen: (modal: SettingsModalKey) => void;
};

const PREVIEW_MAX = 160;

function truncatePreview(text: string, max = PREVIEW_MAX): string {
  const t = (text || '').trim();
  if (!t) return '';
  if (t.length <= max) return t;
  return `${t.slice(0, max - 1)}…`;
}

function basenamePath(path: string): string {
  const p = (path || '').trim();
  if (!p) return '—';
  const parts = p.split(/[/\\]/);
  return parts[parts.length - 1] || p;
}

/** Panel lateral Run settings — estilo Google AI Studio. */
export function PlaygroundRunSettingsPanel({
  config,
  workerId,
  capabilitiesRefreshKey,
  activeVaultPath,
  activeVaultScope,
  workerLabel,
  projectLabel,
  knowledgeScopeLabel,
  systemPreview,
  systemReady,
  invalidWorkers,
  logsPanelOpen,
  onLogsToggle,
  logsControls,
  logsViewport,
  onOpen,
}: PlaygroundRunSettingsPanelProps) {
  const [contextOpen, setContextOpen] = useState(true);
  const [toolsOpen, setToolsOpen] = useState(true);

  const model = config?.llm?.model || '—';
  const provider = config?.llm?.provider || 'Proveedor LLM';
  const slmEnabled = Boolean(config?.slm?.enabled);
  const slmLabel = slmEnabled
    ? `${config?.slm?.model_short || 'MLX'} · ${config?.slm?.mlx_status || '—'}`
    : 'Ninguno';
  const vaultLabel = basenamePath(activeVaultPath);
  const vaultScope =
    activeVaultScope === 'chat' ? 'Por conversación' : 'Vault compartido (RAG + SQL)';

  const bottomPanelOpen = logsPanelOpen;

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col gap-2">
      <div
        className={`scrollbar-thin min-h-0 overflow-y-auto overflow-x-hidden overscroll-contain [scrollbar-gutter:stable] ${
          bottomPanelOpen ? 'max-h-[42%] shrink-0 space-y-3' : 'flex-1 space-y-4'
        }`}
      >
        <button
          type="button"
          onClick={() => onOpen('model')}
          className="w-full rounded-xl border border-gov-gray-200/90 bg-white p-3 text-left transition-colors hover:border-gov-blue-200 hover:bg-gov-blue-50/30 dark:border-dark-border dark:bg-[#1e1f20] dark:hover:border-gov-blue-800 dark:hover:bg-dark-surface"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <p className="text-[10px] font-black uppercase tracking-wider text-gov-gray-400 dark:text-dark-muted">
                LLM
              </p>
              <p className="text-sm font-semibold text-gov-gray-900 dark:text-dark-text">{model}</p>
              <p className="mt-0.5 font-mono text-[11px] text-gov-gray-500 dark:text-dark-muted">
                {provider}
              </p>
              <p className="mt-2 text-[10px] font-black uppercase tracking-wider text-gov-gray-400 dark:text-dark-muted">
                SLM (opcional)
              </p>
              <p className="text-xs font-semibold text-gov-gray-800 dark:text-dark-text">{slmLabel}</p>
              <p className="mt-2 text-[11px] leading-relaxed text-gov-gray-500 dark:text-dark-muted">
                LLM remoto + SLM local MLX-Inference. Clic para cambiar.
              </p>
            </div>
            <div className="flex flex-col gap-1 shrink-0">
              <Brain size={16} className="text-gov-gray-400 dark:text-dark-muted" aria-hidden />
              <Cpu size={16} className="text-gov-gray-400 dark:text-dark-muted" aria-hidden />
            </div>
          </div>
        </button>

        <LlmSecretsBanner gap={config?.llm_gap} className="mt-2" />

        <div>
          <button
            type="button"
            onClick={() => onOpen('instructions')}
            className="w-full min-h-[5.5rem] rounded-xl border border-gov-gray-200/90 bg-white p-3 text-left transition-colors hover:border-gov-blue-200 dark:border-dark-border dark:bg-[#1e1f20] dark:hover:border-gov-blue-800"
          >
            <p className="text-[10px] font-black uppercase tracking-wider text-gov-gray-400 dark:text-dark-muted">
              System instructions
            </p>
            <p
              className={`mt-1.5 text-xs leading-relaxed whitespace-pre-wrap break-words ${
                systemReady
                  ? 'text-gov-gray-700 dark:text-dark-text'
                  : 'text-gov-gray-400 dark:text-dark-muted'
              }`}
            >
              {systemReady
                ? truncatePreview(systemPreview)
                : 'Opcional: tono y comportamiento del agente para este worker.'}
            </p>
            <span className="mt-2 inline-flex items-center gap-1 text-[10px] font-semibold text-gov-blue-700 dark:text-dark-cyan">
              <FileText size={11} aria-hidden />
              {systemReady ? 'Editar' : 'Configurar'}
            </span>
          </button>
        </div>

        <StudioCollapsible
          title="Contexto"
          open={contextOpen}
          onToggle={() => setContextOpen((v) => !v)}
        >
          <StudioFieldRow
            label="DuckDB"
            value={vaultLabel}
            hint={vaultScope}
            mono
            onClick={() => onOpen('vault')}
          />
          <StudioFieldRow
            label="Proyecto"
            value={projectLabel}
            hint="Filtro de agentes"
            onClick={() => onOpen('routing')}
          />
          <StudioFieldRow
            label="RAG"
            value={knowledgeScopeLabel}
            hint="Alcance de conocimiento en chat"
            onClick={() => onOpen('routing')}
          />
          <StudioFieldRow
            label="Agente"
            value={workerLabel}
            hint="Worker de esta conversación"
            onClick={() => onOpen('routing')}
          />
        </StudioCollapsible>

        <StudioCollapsible
          title="Herramientas"
          open={toolsOpen}
          onToggle={() => setToolsOpen((v) => !v)}
        >
          <PlaygroundWorkerCapabilitiesPanel workerId={workerId} refreshKey={capabilitiesRefreshKey} />
          <StudioToggleRow
            label="Logs PM2"
            hint={logsPanelOpen ? 'Consola abajo' : 'Mostrar consola de logs'}
            checked={logsPanelOpen}
            onChange={onLogsToggle}
            icon={<Terminal size={14} aria-hidden />}
          />
          {logsPanelOpen && logsControls ? logsControls : null}
        </StudioCollapsible>

        {invalidWorkers.length > 0 && (
          <p className="rounded-xl border border-amber-200/90 bg-amber-50/80 p-3 text-[11px] font-medium text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
            Agentes no disponibles: {invalidWorkers.join(', ')}.
          </p>
        )}
      </div>

      {logsPanelOpen && logsViewport ? (
        <div className="flex min-h-[140px] max-h-[min(42vh,380px)] min-w-0 shrink-0 flex-col overflow-hidden rounded-xl border border-gov-gray-200/90 bg-white text-gov-gray-800 dark:border-dark-border dark:bg-slate-950 dark:text-slate-200">
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">{logsViewport}</div>
        </div>
      ) : null}
    </div>
  );
}

function StudioCollapsible({
  title,
  open,
  onToggle,
  children,
}: {
  title: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <section className="min-w-0 rounded-xl border border-gov-gray-200/90 bg-white dark:border-dark-border dark:bg-[#1e1f20]">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left"
        aria-expanded={open}
      >
        <span className="text-xs font-semibold text-gov-gray-800 dark:text-dark-text">{title}</span>
        <ChevronDown
          size={14}
          className={`shrink-0 text-gov-gray-400 transition-transform dark:text-dark-muted ${
            open ? 'rotate-0' : '-rotate-90'
          }`}
          aria-hidden
        />
      </button>
      {open ? (
        <div className="space-y-0.5 border-t border-gov-gray-100 px-1 py-1 dark:border-dark-border">
          {children}
        </div>
      ) : null}
    </section>
  );
}

function StudioFieldRow({
  label,
  value,
  hint,
  mono,
  onClick,
}: {
  label: string;
  value: string;
  hint: string;
  mono?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left transition-colors hover:bg-gov-gray-50 dark:hover:bg-dark-bg/80"
    >
      <span className="w-16 shrink-0 text-[11px] font-medium text-gov-gray-500 dark:text-dark-muted">
        {label}
      </span>
      <span className="min-w-0 flex-1">
        <span
          className={`block truncate text-xs font-semibold text-gov-gray-900 dark:text-dark-text ${
            mono ? 'font-mono text-[11px]' : ''
          }`}
          title={value}
        >
          {value}
        </span>
        <span className="block truncate text-[10px] text-gov-gray-500 dark:text-dark-muted" title={hint}>
          {hint}
        </span>
      </span>
      <ChevronRight
        size={14}
        className="shrink-0 text-gov-gray-300 opacity-0 transition-opacity group-hover:opacity-100 dark:text-dark-muted"
        aria-hidden
      />
    </button>
  );
}

function StudioToggleRow({
  label,
  hint,
  checked,
  onChange,
  icon,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onChange: () => void;
  icon?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg px-2 py-2">
      <div className="flex min-w-0 items-start gap-2">
        {icon ? (
          <span className="mt-0.5 text-gov-gray-400 dark:text-dark-muted">{icon}</span>
        ) : null}
        <div className="min-w-0">
          <p className="text-xs font-medium text-gov-gray-800 dark:text-dark-text">{label}</p>
          <p className="text-[10px] text-gov-gray-500 dark:text-dark-muted">{hint}</p>
        </div>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={onChange}
        className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${
          checked ? 'bg-gov-blue-600 dark:bg-gov-blue-500' : 'bg-gov-gray-300 dark:bg-dark-border'
        }`}
      >
        <span
          className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
            checked ? 'translate-x-4' : 'translate-x-0'
          }`}
        />
      </button>
    </div>
  );
}

/** @deprecated Alias interno — tests y imports legacy. */
export const RunSettingsCard = PlaygroundRunSettingsPanel;
