'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { CheckCircle2, KeyRound, Loader2, LogIn, Plug } from 'lucide-react';
import ConfirmModal from '@/components/admin/ConfirmModal';
import {
  adminService,
  type McpConnectorPreset,
  type McpConnectorSummary,
} from '@/services/adminService';
import { pollWriteTask } from '@/lib/pollWriteTask';
import {
  connectorNameSlug,
  existingPresetIdsFromConnectors,
  groupMcpPresetsForSelect,
  presetAdminLabel,
  presetAuthHint,
  presetAuthKindLabel,
  presetConnectorId,
  presetUsesOAuthPkce,
} from '@/lib/mcpPresetAuth';
import { SearchableGroupedSelect } from '@/components/shared/SearchableGroupedSelect';

type McpNewConnectorSectionProps = {
  canWrite: boolean;
  /** Conectores ya materializados: se marcan en el selector. */
  existingConnectors?: Pick<McpConnectorSummary, 'preset_id' | 'connector_id'>[];
  onCreated?: () => void | Promise<void>;
};

function oauthRedirectUri(): string {
  return `${window.location.origin}/api/admin/mcp/connectors/oauth/callback`;
}

export function McpNewConnectorSection({
  canWrite,
  existingConnectors = [],
  onCreated,
}: McpNewConnectorSectionProps) {
  const [presets, setPresets] = useState<McpConnectorPreset[]>([]);
  const [selectedPreset, setSelectedPreset] = useState('');
  const [bearerToken, setBearerToken] = useState('');
  /** Name of an extra connection of a service that already has one (e.g. a second YouTube channel). */
  const [instanceName, setInstanceName] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const existingPresetIds = useMemo(
    () => existingPresetIdsFromConnectors(existingConnectors),
    [existingConnectors]
  );

  const presetGroups = useMemo(() => groupMcpPresetsForSelect(presets), [presets]);

  const selectGroups = useMemo(
    () =>
      presetGroups.map((group) => ({
        id: group.id,
        label: group.label,
        options: group.presets.map((preset) => {
          const created = existingPresetIds.has(preset.preset_id);
          return {
            value: preset.preset_id,
            label: created
              ? `${presetAdminLabel(preset)} (ya creado · agregar otra conexión)`
              : presetAdminLabel(preset),
            meta: presetAuthKindLabel(preset),
          };
        }),
      })),
    [presetGroups, existingPresetIds]
  );

  const loadPresets = useCallback(() => {
    setLoading(true);
    setError(null);
    adminService
      .listMcpConnectorPresets()
      .then((presetRows) => {
        setPresets(presetRows);
        setSelectedPreset((prev) => {
          if (prev && presetRows.some((p) => p.preset_id === prev)) return prev;
          const groups = groupMcpPresetsForSelect(presetRows);
          const firstAvailable = groups
            .flatMap((g) => g.presets)
            .find((p) => !existingPresetIdsFromConnectors(existingConnectors).has(p.preset_id));
          return firstAvailable?.preset_id || presetRows[0]?.preset_id || '';
        });
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'No se pudieron cargar plantillas'))
      .finally(() => setLoading(false));
  }, [existingConnectors]);

  useEffect(() => {
    loadPresets();
  }, [loadPresets]);

  const presetById = useMemo(
    () => Object.fromEntries(presets.map((preset) => [preset.preset_id, preset])),
    [presets]
  );

  const selected = selectedPreset ? presetById[selectedPreset] : undefined;
  const alreadyCreated = Boolean(selectedPreset && existingPresetIds.has(selectedPreset));
  const baseId = selected ? presetConnectorId(selected) : selectedPreset ? `mcp_${selectedPreset}` : '';
  // A second connection of the same service gets its own id, OAuth token and tools (mcp__<id>__<tool>);
  // its name goes into every tool description, so the agent can tell the connections apart.
  const instanceSlug = connectorNameSlug(instanceName);
  const previewId = alreadyCreated ? (instanceSlug ? `${baseId}_${instanceSlug}` : '') : baseId;
  const idTaken = Boolean(previewId && existingConnectors.some((c) => c.connector_id === previewId));
  const baseName = selected ? presetAdminLabel(selected) : selectedPreset;
  const previewName =
    alreadyCreated && instanceName.trim() ? `${baseName} · ${instanceName.trim()}` : baseName;
  const instanceMissing = alreadyCreated && (!instanceSlug || idTaken);
  const needsOAuth = selected ? presetUsesOAuthPkce(selected) : false;
  const needsBearer = Boolean(selected && !needsOAuth && selected.auth_kind === 'bearer');

  const primaryLabel = alreadyCreated
    ? needsOAuth
      ? 'Agregar conexión y conectar OAuth'
      : 'Agregar conexión'
    : needsOAuth
      ? 'Crear y conectar OAuth'
      : needsBearer
        ? 'Crear y guardar token'
        : 'Crear conector';

  const materializeConnector = async (): Promise<string> => {
    const result = await adminService.createMcpConnector(
      alreadyCreated
        ? { preset_id: selectedPreset, connector_id: previewId, display_name: previewName }
        : { preset_id: selectedPreset }
    );
    if (result.task_id) {
      const polled = await pollWriteTask(result.task_id);
      if (polled.state === 'failed') {
        throw new Error(polled.detail || 'La creación no se aplicó en DB');
      }
      if (polled.state === 'timeout' || polled.state === 'not_found') {
        throw new Error(
          polled.state === 'timeout'
            ? 'Creación encolada pero no confirmada (db-writer / lock DuckDB). Reintenta.'
            : 'No se confirmó la creación. Refresca la lista o reintenta.'
        );
      }
    }
    // The create response falls back to the newest row when its read races the writer: trust the id we asked for.
    return previewId || result.connector?.connector_id || baseId;
  };

  const createFromPreset = async () => {
    if (!selectedPreset || busy || instanceMissing) return;
    if (needsBearer && !bearerToken.trim()) {
      setError('Pega el token Bearer antes de crear el conector.');
      setConfirmOpen(false);
      return;
    }

    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const connectorId = await materializeConnector();

      if (needsBearer) {
        await adminService.setMcpConnectorAuth(connectorId, bearerToken.trim());
        setBearerToken('');
        setSuccess(`Conector «${previewName || connectorId}» creado y autenticado con Bearer.`);
        await onCreated?.();
        return;
      }

      if (needsOAuth) {
        const isGoogleWorkspace =
          selected?.metadata?.oauth_provider === 'google_workspace' ||
          selectedPreset.startsWith('google_');
        await onCreated?.();
        const oauth = await adminService.startMcpConnectorOAuth(
          connectorId,
          isGoogleWorkspace ? '' : oauthRedirectUri()
        );
        window.location.href = oauth.authorization_url;
        return;
      }

      setSuccess(`Conector «${previewName || connectorId}» creado (${connectorId}).`);
      await onCreated?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo crear el conector');
    } finally {
      setBusy(false);
      setConfirmOpen(false);
    }
  };

  if (!canWrite) {
    return null;
  }

  if (loading) {
    return <p className="text-sm text-gov-gray-500">Cargando plantillas MCP…</p>;
  }

  return (
    <>
      <ConfirmModal
        isOpen={confirmOpen}
        title={primaryLabel}
        description={
          needsOAuth
            ? 'Se crea el conector y se abre el flujo OAuth del proveedor.'
            : needsBearer
              ? 'Se crea el conector y se guarda el token Bearer como secreto.'
              : 'Se materializa una instancia en DuckDB desde la plantilla elegida.'
        }
        confirmLabel={needsOAuth ? 'Sí, crear y conectar' : 'Sí, crear'}
        isLoading={busy}
        details={[
          { label: 'MCP', value: previewName || selectedPreset },
          { label: 'ID', value: previewId || '—' },
          { label: 'Auth', value: selected ? presetAuthKindLabel(selected) : '—' },
        ]}
        onConfirm={() => void createFromPreset()}
        onCancel={() => {
          if (!busy) setConfirmOpen(false);
        }}
      />

      {error ? (
        <p className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
          {error}
        </p>
      ) : null}
      {success ? (
        <div className="mb-4 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-900 dark:border-green-900/50 dark:bg-green-950/20 dark:text-green-200">
          <div className="flex items-start gap-2 font-bold">
            <CheckCircle2 size={16} className="mt-0.5 shrink-0" aria-hidden />
            <span>{success}</span>
          </div>
        </div>
      ) : null}

      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex min-w-[280px] flex-1 flex-col gap-1 text-xs font-bold uppercase tracking-wide text-gov-gray-500">
            MCP
            <SearchableGroupedSelect
              value={selectedPreset}
              groups={selectGroups}
              onChange={(next) => {
                setSelectedPreset(next);
                setBearerToken('');
                setInstanceName('');
                setSuccess(null);
                setError(null);
              }}
              placeholder="Buscar o elegir MCP…"
              searchPlaceholder="Buscar por nombre, auth, host…"
              emptyLabel="Ningún MCP coincide con la búsqueda"
              aria-label="Elegir plantilla MCP"
              className="font-normal normal-case"
            />
          </label>
          <button
            type="button"
            onClick={() => {
              setError(null);
              setConfirmOpen(true);
            }}
            disabled={
              !selectedPreset ||
              busy ||
              instanceMissing ||
              (needsBearer && !bearerToken.trim())
            }
            className="inline-flex items-center gap-2 rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50 dark:bg-dark-cyan dark:text-dark-bg"
          >
            {busy ? (
              <Loader2 size={16} className="animate-spin" />
            ) : needsOAuth ? (
              <LogIn size={16} />
            ) : needsBearer ? (
              <KeyRound size={16} />
            ) : (
              <Plug size={16} />
            )}
            {primaryLabel}
          </button>
        </div>

        {selected ? (
          <p className="text-xs text-gov-gray-600 dark:text-dark-muted">
            {alreadyCreated
              ? 'Ya tienes una conexión de este MCP. Para otra cuenta o canal, ponle un nombre: el agente verá las dos y elegirá por ese nombre. Después dale el grant al worker en la lista de abajo.'
              : needsOAuth
                ? 'Al confirmar se crea el conector y se abre OAuth del proveedor.'
                : needsBearer
                  ? 'Pega el token y confirma: se crea el conector y se guarda el secreto.'
                  : presetAuthHint(selected)}
          </p>
        ) : null}

        {alreadyCreated ? (
          <label className="flex max-w-xl flex-col gap-1 text-xs font-bold uppercase tracking-wide text-gov-gray-500">
            Nombre de la nueva conexión
            <input
              type="text"
              value={instanceName}
              onChange={(e) => setInstanceName(e.target.value)}
              placeholder="p. ej. Canal History & Machine"
              maxLength={60}
              className="rounded-xl border border-gov-gray-200 bg-white px-3 py-2 text-sm font-normal normal-case dark:border-dark-border dark:bg-dark-bg"
            />
            {idTaken ? (
              <span className="font-normal normal-case text-red-600">Ya existe una conexión con ese nombre.</span>
            ) : null}
          </label>
        ) : null}

        {needsBearer ? (
          <label className="flex max-w-xl flex-col gap-1 text-xs font-bold uppercase tracking-wide text-gov-gray-500">
            Token Bearer
            <input
              type="password"
              autoComplete="off"
              value={bearerToken}
              onChange={(e) => setBearerToken(e.target.value)}
              placeholder="pega el token aquí"
              className="rounded-xl border border-gov-gray-200 bg-white px-3 py-2 text-sm font-normal normal-case dark:border-dark-border dark:bg-dark-bg"
            />
          </label>
        ) : null}
      </div>
    </>
  );
}
