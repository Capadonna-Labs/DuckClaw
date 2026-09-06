/**
 * Turno de chat playground (SSE): tokens, heartbeats, TTS, loop follow-up.
 * Separado de useAdminChat para SoC — el hook solo inyecta estado/refs.
 */
import type { Dispatch, MutableRefObject, SetStateAction } from 'react';

import { adminService } from '@/services/adminService';
import { friendlyGatewayError } from '@/lib/adminErrors';
import type { ChatImagePreview, ChatMsg } from '@/components/chat/types';
import { userPreviewsFromPayload } from '@/lib/chatMessageImages';
import { requestNotificationPermission } from '@/lib/chatNotifications';
import { playTtsAudio, primeAudioPlayback, type TtsAudioFormat } from '@/lib/playTtsAudio';
import {
  finalizeRunningToolHeartbeats,
  createToolInvocationId,
  findRunningToolHeartbeatIndex,
  mapSseToolPhase,
  parseToolNameFromHeartbeatText,
  toolHeartbeatDisplayText,
} from '@/lib/toolHeartbeat';

import {
  applyLastTurnTokenDisplay,
  artifactImagePreview,
  isLoopProgressHeartbeat,
  shouldFetchChatSuggestions,
  stripThinkingStatusHeartbeats,
} from './adminChatPure';
import type { UsageTokenBreakdown } from '@/lib/formatTokenCount';

export type ThinkingIdentity = { workerId: string; swarmSlot: number };

export type RunAdminChatTurnParams = {
  text: string;
  payloadImages?: { mime_type: string; data_base64: string }[];
  payloadDocuments?: { filename: string; mime_type: string; data_base64: string }[];
  userPreviewImages?: ChatImagePreview[];
  documentNames?: string[];
  chatId: string;
  workerId: string;
  projectId: string;
  knowledgeScope: string;
  vaultPath: string;
  voiceResponseMode: boolean;
  effectiveTenantId?: string;
  telegramUserId?: string;
  abortControllerRef: MutableRefObject<AbortController | null>;
  thinkingStartedAt: MutableRefObject<number>;
  setLoading: Dispatch<SetStateAction<boolean>>;
  setThinking: Dispatch<SetStateAction<boolean>>;
  setThinkingIdentity: Dispatch<SetStateAction<ThinkingIdentity>>;
  setError: Dispatch<SetStateAction<string | null>>;
  setMessages: Dispatch<SetStateAction<ChatMsg[]>>;
  setLastTurnUsage: Dispatch<SetStateAction<UsageTokenBreakdown | null>>;
  setContextEstimatedTokens: Dispatch<SetStateAction<number | null>>;
  setLoopSchedulePolling: Dispatch<SetStateAction<boolean>>;
  setSuggestions: Dispatch<SetStateAction<string[]>>;
  finalizeCancelledGeneration: () => void;
  clearLoopHistoryReload: () => void;
  scheduleLoopHistoryReload: () => void;
  onConversationActivity?: () => void;
  onSandboxArtifacts?: (payload: {
    sandbox_run_id?: string;
    artifact_ids?: string[];
  }) => void;
};

export async function runAdminChatTurn(params: RunAdminChatTurnParams): Promise<void> {
  const {
    text,
    payloadImages = [],
    payloadDocuments = [],
    userPreviewImages = [],
    documentNames = [],
    chatId,
    workerId,
    projectId,
    knowledgeScope,
    vaultPath,
    voiceResponseMode,
    effectiveTenantId,
    telegramUserId,
    abortControllerRef,
    thinkingStartedAt,
    setLoading,
    setThinking,
    setThinkingIdentity,
    setError,
    setMessages,
    setLastTurnUsage,
    setContextEstimatedTokens,
    setLoopSchedulePolling,
    setSuggestions,
    finalizeCancelledGeneration,
    clearLoopHistoryReload,
    scheduleLoopHistoryReload,
    onConversationActivity,
    onSandboxArtifacts,
  } = params;


if (!text && payloadImages.length === 0 && payloadDocuments.length === 0) return;
void requestNotificationPermission();
abortControllerRef.current?.abort();
const abortController = new AbortController();
abortControllerRef.current = abortController;

const userPreviews =
  userPreviewImages.length > 0
    ? userPreviewImages
    : payloadImages.length > 0
      ? userPreviewsFromPayload(payloadImages)
      : undefined;
const docLabels =
  documentNames.length > 0
    ? documentNames
    : payloadDocuments.map((d) => d.filename).filter(Boolean);
const userLabel = text;
let loopFollowUp = /^\/(loop|meditate)\b/i.test(text.trim());

setLoading(true);
thinkingStartedAt.current = Date.now();
setThinkingIdentity({ workerId, swarmSlot: 1 });
setThinking(true);
setError(null);
setSuggestions([]);
setMessages((m) => [
  ...m,
  {
    role: 'user',
    text: userLabel,
    imagePreviews: userPreviews?.length ? userPreviews : undefined,
    documentNames: docLabels.length ? docLabels : undefined,
  },
  { role: 'assistant', text: '', streaming: true },
]);

const appendAssistant = (chunk: string) => {
  if (chunk) setThinking(false);
  setMessages((m) => {
    if (m.length === 0) return m;
    const next = [...m];
    const last = next[next.length - 1];
    if (last?.role !== 'assistant') return m;
    next[next.length - 1] = { ...last, text: last.text + chunk, streaming: true };
    return next;
  });
};

const attachArtifactToStreamingAssistant = (
  artifactId: string,
  tenantId: string
) => {
  const previews = artifactImagePreview(tenantId, artifactId);
  setThinking(false);
  setMessages((m) => {
    const idx = m.findIndex(
      (x, i) => x.role === 'assistant' && x.streaming && i === m.length - 1
    );
    if (idx < 0) return m;
    const next = [...m];
    next[idx] = { ...next[idx], imagePreviews: previews };
    return next;
  });
};

const appendHeartbeat = (payload: {
  text: string;
  kind?: 'plan' | 'tool' | 'status' | 'visual' | 'loop_tick';
  worker_id?: string;
  swarm_slot?: number;
  artifact_id?: string;
  artifact_tenant_id?: string;
  sandbox_run_id?: string;
  artifact_ids?: string[];
  tool_name?: string;
  tool_phase?: 'start' | 'done' | 'error';
  elapsed_ms?: number;
}) => {
  const kind = payload.kind ?? 'status';
  if (
    kind === 'visual' &&
    (payload.sandbox_run_id?.trim() || (payload.artifact_ids?.length ?? 0) > 0)
  ) {
    onSandboxArtifacts?.({
      sandbox_run_id: payload.sandbox_run_id,
      artifact_ids: payload.artifact_ids,
    });
  }
  const hbWorker = (payload.worker_id || workerId || '').trim();
  const hbSlot =
    payload.swarm_slot != null && Number.isFinite(payload.swarm_slot)
      ? Math.max(1, Math.floor(payload.swarm_slot))
      : 1;
  if (hbWorker || hbSlot > 1) {
    setThinkingIdentity((prev) => ({
      workerId: hbWorker || prev.workerId || workerId,
      swarmSlot: hbSlot,
    }));
  }
  const aid = (payload.artifact_id || '').trim();
  if (aid) {
    const tid =
      (payload.artifact_tenant_id || effectiveTenantId || 'default').trim() ||
      'default';
    void attachArtifactToStreamingAssistant(aid, tid);
  }
  const toolName =
    (payload.tool_name || '').trim() ||
    parseToolNameFromHeartbeatText(payload.text) ||
    undefined;
  let effectiveKind = kind;
  if (effectiveKind === 'tool' && !toolName) {
    // Heartbeat legacy (p. ej. noVNC) sin tool_name: no crear bloque "Usando: tool".
    effectiveKind = 'status';
  }
  const uiPhase = mapSseToolPhase(payload.tool_phase);
  const isToolHb = effectiveKind === 'tool' && Boolean(toolName);
  if (kind === 'tool') {
    setThinking(false);
  }
  setMessages((m) => {
    const streamingIdx = m.findIndex(
      (x, i) => x.role === 'assistant' && x.streaming && i === m.length - 1
    );
    const insertAt = streamingIdx >= 0 ? streamingIdx : m.length;
    const elapsedMs =
      payload.tool_phase === 'done' || payload.tool_phase === 'error'
        ? payload.elapsed_ms
        : undefined;

    if (isToolHb && toolName) {
      const isStart = payload.tool_phase === 'start' || uiPhase === 'running';
      const runningIdx = findRunningToolHeartbeatIndex(m, toolName, insertAt);
      const running = runningIdx >= 0 ? m[runningIdx] : null;

      if (isStart) {
        if (running) {
          const merged: ChatMsg = {
            ...running,
            text: toolHeartbeatDisplayText(toolName, 'running', undefined),
            toolPhase: 'running',
            workerId: hbWorker || running.workerId,
            swarmSlot: hbSlot,
          };
          const next = [...m];
          next[runningIdx] = merged;
          return next;
        }
        const startedAt = Date.now();
        const merged: ChatMsg = {
          role: 'heartbeat',
          text: toolHeartbeatDisplayText(toolName, 'running', undefined),
          heartbeatKind: 'tool',
          workerId: hbWorker || undefined,
          swarmSlot: hbSlot,
          toolName,
          toolInvocationId: createToolInvocationId(toolName),
          toolPhase: 'running',
          toolStartedAt: startedAt,
        };
        const next = [...m];
        next.splice(insertAt, 0, merged);
        return next;
      }

      const targetIdx = runningIdx;
      const existing = targetIdx >= 0 ? m[targetIdx] : null;
      const startedAt = existing?.toolStartedAt ?? Date.now();
      const merged: ChatMsg = {
        role: 'heartbeat',
        text: toolHeartbeatDisplayText(toolName, uiPhase, elapsedMs),
        heartbeatKind: 'tool',
        workerId: hbWorker || existing?.workerId,
        swarmSlot: hbSlot,
        toolName,
        toolInvocationId: existing?.toolInvocationId ?? createToolInvocationId(toolName),
        toolPhase: uiPhase ?? 'done',
        toolStartedAt: startedAt,
        toolElapsedMs:
          elapsedMs != null && Number.isFinite(elapsedMs) ? elapsedMs : undefined,
      };
      if (targetIdx >= 0) {
        const next = [...m];
        next[targetIdx] = merged;
        return next;
      }
      const next = [...m];
      next.splice(insertAt, 0, merged);
      return next;
    }

    const hb: ChatMsg = {
      role: 'heartbeat',
      text: payload.text,
      heartbeatKind: effectiveKind,
      workerId: hbWorker || undefined,
      swarmSlot: hbSlot,
    };
    if (streamingIdx >= 0) {
      const next = [...m];
      next.splice(streamingIdx, 0, hb);
      return next;
    }
    return [...m, hb];
  });
  if (
    (effectiveKind === 'status' || payload.kind === 'loop_tick') &&
    (isLoopProgressHeartbeat(payload.text) || payload.kind === 'loop_tick')
  ) {
    setLoopSchedulePolling(true);
    scheduleLoopHistoryReload();
  }
};

primeAudioPlayback();
let authoritativeResponse = '';
try {
  let assignedSuffix = '';
  let elapsedFooter = '';
  const streamAudioRef: {
    current: {
      audioBase64?: string;
      audioFormat?: TtsAudioFormat;
      audioUnavailable?: boolean;
    } | null;
  } = { current: null };
  const streamVisual: {
    figure_base64?: string;
    fly_charts_b64?: string[];
    fly_chart_artifact_ids?: string[];
    fly_chart_names?: string[];
    artifact_id?: string;
    artifact_tenant_id?: string;
  } = {};
  await adminService.playgroundChatStream(
    {
      worker_id: workerId,
      project_id: projectId || undefined,
      knowledge_scope: knowledgeScope || undefined,
      message: text,
      chat_id: chatId,
          tenant_id: effectiveTenantId ?? 'default',
          telegram_user_id: telegramUserId,
      vault_db_path: vaultPath || undefined,
      images: payloadImages.length ? payloadImages : undefined,
      documents: payloadDocuments.length ? payloadDocuments : undefined,
      voice_response: voiceResponseMode,
    },
    {
      onToken: appendAssistant,
      onHeartbeat: appendHeartbeat,
      onAudio: (payload) => {
        streamAudioRef.current = {
          audioBase64: payload.audio_base64,
          audioFormat: payload.audio_format,
          audioUnavailable: Boolean(payload.audio_unavailable),
        };
      },
      onDone: (meta) => {
        applyLastTurnTokenDisplay(setLastTurnUsage, setContextEstimatedTokens, meta);
        if ((meta.response || '').trim()) {
          authoritativeResponse = meta.response.trim();
        }
        if (
          authoritativeResponse.includes('Ciclo loop iniciado') ||
          authoritativeResponse.includes('Ciclo meditate iniciado') ||
          authoritativeResponse.includes('Modo /loop activo') ||
          authoritativeResponse.includes('Modo /meditate activo')
        ) {
          loopFollowUp = true;
          setLoopSchedulePolling(true);
        }
        const respLower = authoritativeResponse.toLowerCase();
        if (
          respLower.includes('modo /loop') &&
          (respLower.includes('inactivo') || respLower.includes('detenido'))
        ) {
          setLoopSchedulePolling(false);
          clearLoopHistoryReload();
        }
        if (meta.assigned_worker_id && meta.assigned_worker_id !== workerId) {
          assignedSuffix = ` (worker: ${meta.assigned_worker_id})`;
        }
        if (meta.elapsed_ms != null && Number.isFinite(meta.elapsed_ms)) {
          elapsedFooter = `\n\nTiempo: ${(meta.elapsed_ms / 1000).toFixed(2)}s`;
        }
        if (
          meta.figure_base64 ||
          meta.fly_charts_b64?.length ||
          meta.fly_chart_artifact_ids?.length ||
          meta.artifact_id
        ) {
          streamVisual.figure_base64 = meta.figure_base64;
          streamVisual.fly_charts_b64 = meta.fly_charts_b64;
          streamVisual.fly_chart_artifact_ids = meta.fly_chart_artifact_ids;
          streamVisual.fly_chart_names = meta.fly_chart_names;
          streamVisual.artifact_id = meta.artifact_id;
          streamVisual.artifact_tenant_id = meta.artifact_tenant_id;
        }
      },
    },
    { signal: abortController.signal }
  );
  if (abortController.signal.aborted) {
    finalizeCancelledGeneration();
    return;
  }
  const capturedStreamAudio = streamAudioRef.current;
  const tenantForArtifact =
    (streamVisual.artifact_tenant_id || effectiveTenantId || 'default').trim() ||
    'default';
  let assistantPreviews: ChatMsg['imagePreviews'] | undefined;
  const chartNamesFromStream = (streamVisual.fly_chart_names ?? []).filter((n) => n?.trim());
  const defaultChartNames = ['metrics-overview.png', 'participation-pie.png'];
  const chartNameAt = (index: number) =>
    chartNamesFromStream[index] ?? defaultChartNames[index] ?? `chart-${index + 1}.png`;
  const artifactIdsFromFly = (streamVisual.fly_chart_artifact_ids ?? []).filter((id) =>
    id?.trim()
  );
  const chartsFromFly = (streamVisual.fly_charts_b64 ?? []).filter((b) => b?.trim());
  if (artifactIdsFromFly.length > 0) {
    assistantPreviews = artifactIdsFromFly.flatMap((aid, i) =>
      artifactImagePreview(tenantForArtifact, aid).map((p) => ({
        ...p,
        name: chartNameAt(i),
      }))
    );
  } else if (chartsFromFly.length > 0) {
    assistantPreviews = chartsFromFly.map((b64, i) => {
      const raw = b64.trim();
      const src = raw.startsWith('data:') ? raw : `data:image/png;base64,${raw}`;
      return { url: src, name: chartNameAt(i) };
    });
  } else if (streamVisual.figure_base64?.trim()) {
    const raw = streamVisual.figure_base64.trim();
    const src = raw.startsWith('data:') ? raw : `data:image/png;base64,${raw}`;
    assistantPreviews = [{ url: src, name: 'imagen-generada.png' }];
  } else if (streamVisual.artifact_id) {
    assistantPreviews = artifactImagePreview(tenantForArtifact, streamVisual.artifact_id);
  }
  setMessages((m) => {
    if (m.length === 0) return m;
    const next = [...m];
    const last = next[next.length - 1];
    if (last?.role === 'assistant') {
      const streamed = (last.text || '').trim();
      const base =
        authoritativeResponse.length > streamed.length
          ? authoritativeResponse
          : streamed || '(sin respuesta)';
      next[next.length - 1] = {
        role: 'assistant',
        text: base + assignedSuffix + elapsedFooter,
        streaming: false,
        imagePreviews: assistantPreviews ?? last.imagePreviews,
        audioBase64: capturedStreamAudio?.audioBase64,
        audioFormat: capturedStreamAudio?.audioFormat,
        audioUnavailable: capturedStreamAudio?.audioUnavailable,
      };
    }
    return finalizeRunningToolHeartbeats(stripThinkingStatusHeartbeats(next));
  });
  if (capturedStreamAudio?.audioBase64) {
    const playResult = await playTtsAudio(capturedStreamAudio.audioBase64, {
      format: capturedStreamAudio.audioFormat,
      source: 'chat-sse',
    });
    if (!playResult.ok) {
      setMessages((m) => {
        if (m.length === 0) return m;
        const next = [...m];
        const last = next[next.length - 1];
        if (last?.role === 'assistant') {
          next[next.length - 1] = {
            ...last,
            audioPlayError: playResult.reason,
          };
        }
        return next;
      });
    }
  }
} catch (e) {
  if (abortController.signal.aborted) {
    finalizeCancelledGeneration();
    return;
  }
  const msg = friendlyGatewayError(e instanceof Error ? e.message : 'Error');
  setMessages((m) => {
    const trimmed =
      m.length > 0 && m[m.length - 1]?.role === 'assistant' && m[m.length - 1]?.streaming
        ? m.slice(0, -1)
        : m;
    return finalizeRunningToolHeartbeats(stripThinkingStatusHeartbeats([...trimmed, { role: 'error', text: msg }]));
  });
  setError(msg);
} finally {
  if (abortControllerRef.current === abortController) {
    abortControllerRef.current = null;
  }
  setLoading(false);
  setThinking(false);
  if (loopFollowUp && !abortController.signal.aborted) {
    scheduleLoopHistoryReload();
  }
  if (shouldFetchChatSuggestions(text, authoritativeResponse, abortController.signal.aborted)) {
    void adminService
      .getChatSuggestions({
        chat_id: chatId,
        tenant_id: effectiveTenantId,
        last_user_message: text,
        last_assistant_message: authoritativeResponse,
      })
      .then((r) => setSuggestions(r.suggestions ?? []))
      .catch(() => {});
  }
  onConversationActivity?.();
}
}
