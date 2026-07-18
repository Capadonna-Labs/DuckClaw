import { adminFetch } from './http';

export interface TrainTraceFile {
  relative_path: string;
  size_bytes: number;
  line_count: number;
}

export interface TrainStatus {
  trace_format: string;
  paths: Record<string, string>;
  files: Record<string, { exists: boolean; path: string; size_bytes?: number; modified_utc?: string }>;
  conversation_traces: { file_count: number; recent: TrainTraceFile[] };
  gemma4_sanitized: { file_count: number; recent: TrainTraceFile[] };
  pipeline: { sft: string[]; grpo: string[] };
  docs: string[];
}

export interface TrainPipelineResult {
  ok: boolean;
  exit_code?: number;
  stdout?: string;
  stderr?: string;
  records?: number;
  stats?: Record<string, unknown>;
}

export const trainApi = {
  getTrainStatus: () => adminFetch<TrainStatus>('/train/status'),

  getTrainTraceSample: (lake: 'conversation_traces' | 'gemma4', relativePath: string, limit = 5) =>
    adminFetch<{
      lake: string;
      relative_path: string;
      total_lines_estimate: number;
      samples: unknown[];
    }>(
      `/train/traces/sample?lake=${encodeURIComponent(lake)}&relative_path=${encodeURIComponent(relativePath)}&limit=${limit}`
    ),

  trainCollect: (requireValidSql = true) =>
    adminFetch<TrainPipelineResult>('/train/pipeline/collect', {
      method: 'POST',
      body: JSON.stringify({ require_valid_sql: requireValidSql }),
    }),

  trainSanitize: (dryRun = false) =>
    adminFetch<TrainPipelineResult>('/train/pipeline/sanitize', {
      method: 'POST',
      body: JSON.stringify({ dry_run: dryRun }),
    }),

  trainMaterialize: () =>
    adminFetch<TrainPipelineResult>('/train/pipeline/materialize', {
      method: 'POST',
      body: JSON.stringify({}),
    }),

  trainRun: (useLoraConfig = true) =>
    adminFetch<TrainPipelineResult>('/train/pipeline/run', {
      method: 'POST',
      body: JSON.stringify({ use_lora_config: useLoraConfig }),
    }),
};
