'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, Plug } from 'lucide-react';
import {
  adminService,
  type McpConnectorPreset,
} from '@/services/adminService';
import {
  presetAdminLabel,
  presetAuthHint,
  presetAuthKindLabel,
  presetConnectorId,
  presetEgressSummary,
  presetTransportLabel,
} from '@/lib/mcpPresetAuth';

type McpNewConnectorSectionProps = {
  canWrite: boolean;
  onCreated?: () => void;
};

function PresetHint({ preset }: { preset: McpConnectorPreset }) {
  const authHint = presetAuthHint(preset);

  return (
    <div className="mt-4 rounded-2xl bg-gov-gray-50 p-4 text-sm dark:bg-dark-bg">
      <p className="font-mono text-xs text-gov-gray-500 dark:text-dark-muted">
        Identificador:{' '}
        <span className="font-bold text-gov-gray-800 dark:text-dark-text">{presetConnectorId(preset)}</span>
      </p>
      <dl className="mt-3 grid gap-2 sm:grid-cols-2">
        <div>
          <dt className="text-xs font-bold uppercase text-gov-gray-500">Transporte</dt>
          <dd>{presetTransportLabel(preset)}</dd>
        </div>
        <div>
          <dt className="text-xs font-bold uppercase text-gov-gray-500">Autenticación</dt>
          <dd>{presetAuthKindLabel(preset)}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-xs font-bold uppercase text-gov-gray-500">Red</dt>
          <dd>{presetEgressSummary(preset)}</dd>
        </div>
      </dl>
      <p className="mt-2 text-xs text-gov-gray-600 dark:text-dark-muted">{authHint}</p>
    </div>
  );
}

export function McpNewConnectorSection({ canWrite, onCreated }: McpNewConnectorSectionProps) {
  const [presets, setPresets] = useState<McpConnectorPreset[]>([]);
  const [selectedPreset, setSelectedPreset] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadPresets = useCallback(() => {
    setLoading(true);
    setError(null);
    adminService
      .listMcpConnectorPresets()
      .then((presetRows) => {
        setPresets(presetRows);
        setSelectedPreset((prev) => prev || presetRows[0]?.preset_id || '');
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'No se pudieron cargar plantillas'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadPresets();
  }, [loadPresets]);

  const presetById = useMemo(
    () => Object.fromEntries(presets.map((preset) => [preset.preset_id, preset])),
    [presets]
  );

  const createFromPreset = async () => {
    if (!selectedPreset || busy) return;
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      await adminService.createMcpConnector({ preset_id: selectedPreset });
      const id = presetById[selectedPreset]
        ? presetConnectorId(presetById[selectedPreset])
        : `mcp_${selectedPreset}`;
      setSuccess(`Conector ${id} creado. Autoriza y asigna agentes en la pestaña Conectores.`);
      onCreated?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo crear el conector');
    } finally {
      setBusy(false);
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
      {error ? (
        <p className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
          {error}
        </p>
      ) : null}
      {success ? (
        <p className="mb-4 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800 dark:border-green-900/50 dark:bg-green-950/20 dark:text-green-200">
          {success}
        </p>
      ) : null}
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs font-bold uppercase tracking-wide text-gov-gray-500">
          Plantilla MCP
          <select
            value={selectedPreset}
            onChange={(e) => setSelectedPreset(e.target.value)}
            className="min-w-[220px] rounded-xl border border-gov-gray-200 bg-white px-3 py-2 text-sm font-normal normal-case dark:border-dark-border dark:bg-dark-bg"
          >
            {presets.map((preset) => (
              <option key={preset.preset_id} value={preset.preset_id}>
                {presetAdminLabel(preset)}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => void createFromPreset()}
          disabled={!selectedPreset || busy}
          className="inline-flex items-center gap-2 rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50 dark:bg-dark-cyan dark:text-dark-bg"
        >
          {busy ? <Loader2 size={16} className="animate-spin" /> : <Plug size={16} />}
          Crear conector
        </button>
      </div>
      {selectedPreset && presetById[selectedPreset] ? (
        <PresetHint preset={presetById[selectedPreset]} />
      ) : null}
    </>
  );
}
