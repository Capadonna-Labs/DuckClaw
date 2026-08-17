/** Proveedores seleccionables desde la UI admin (alineado con gateway /model). */
export const SELECTABLE_LLM_PROVIDERS = new Set([
  'mlx',
  'ollama',
  'openai',
  'anthropic',
  'deepseek',
  'groq',
  'gemini',
  'openrouter',
]);

/** Alias histórico: MLX es proveedor LLM local (MLX-Inference), no el SLM opcional. */
export const LLM_ONLY_PROVIDERS = SELECTABLE_LLM_PROVIDERS;

/** Slugs OpenRouter con etiqueta legible (id = valor enviado al gateway). */
export const OPENROUTER_MODEL_PRESETS: { id: string; label: string }[] = [
  { id: 'openrouter/free', label: 'OpenRouter Free (auto-routing)' },
  { id: 'nvidia/nemotron-3-nano-30b-a3b:free', label: 'Nemotron 3 Nano 30B (free)' },
  { id: 'nvidia/nemotron-3-super-120b-a12b:free', label: 'Nemotron 3 Super 120B (free)' },
  { id: 'nvidia/nemotron-3-ultra-550b-a55b:free', label: 'Nemotron 3 Ultra 550B (free)' },
  { id: 'google/gemma-2-9b-it:free', label: 'Gemma 2 9B (free)' },
  { id: 'meta-llama/llama-3.2-3b-instruct:free', label: 'Llama 3.2 3B Instruct (free)' },
  { id: 'arcee-ai/trinity-large-preview:free', label: 'Trinity Large Preview (free)' },
  { id: 'z-ai/glm-5.2', label: 'GLM 5.2 (Z.ai)' },
  { id: 'deepseek/deepseek-v4-flash', label: 'DeepSeek V4 Flash' },
  { id: 'deepseek/deepseek-v4-pro', label: 'DeepSeek V4 Pro' },
  { id: 'deepseek/deepseek-chat', label: 'DeepSeek Chat (legacy)' },
  { id: 'deepseek/deepseek-r1', label: 'DeepSeek R1' },
  { id: 'anthropic/claude-sonnet-4-5', label: 'Claude Sonnet 4.5' },
  { id: 'anthropic/claude-3.5-haiku', label: 'Claude 3.5 Haiku' },
  { id: 'google/gemini-2.5-pro', label: 'Gemini 2.5 Pro' },
  { id: 'google/gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
  { id: 'openai/gpt-4o-mini', label: 'GPT-4o mini' },
  { id: 'openai/gpt-4o', label: 'GPT-4o' },
  { id: 'meta-llama/llama-3.3-70b-instruct', label: 'Llama 3.3 70B Instruct' },
  { id: 'qwen/qwen3-235b-a22b', label: 'Qwen3 235B' },
];

const OPENROUTER_LABEL_BY_ID = Object.fromEntries(
  OPENROUTER_MODEL_PRESETS.map((p) => [p.id, p.label])
) as Record<string, string>;

const MLX_FOREIGN_MODEL_PREFIXES = [
  'z-ai/',
  'anthropic/',
  'openai/',
  'google/',
  'deepseek/',
  'meta-llama/',
  'nvidia/',
  'qwen/',
  'arcee-ai/',
];

/** Modelos HF MLX sugeridos (mlx_lm / MLX-Inference). */
export const MLX_MODEL_PRESETS: string[] = [
  'mlx-community/Qwen2.5-Coder-3B-Instruct-4bit',
  'mlx-community/Qwen2.5-7B-Instruct-4bit',
  'mlx-community/Llama-3.2-3B-Instruct-4bit',
  'mlx-community/Llama-3.3-70B-Instruct-4bit',
  'mlx-community/gemma-4-e4b-it-4bit',
];

/** Modelos sugeridos por proveedor (complementa model_example del catálogo). */
export const LLM_MODEL_PRESETS: Record<string, string[]> = {
  deepseek: ['deepseek-v4-flash', 'deepseek-v4-pro', 'deepseek-chat', 'deepseek-reasoner'],
  openai: ['gpt-4o-mini', 'gpt-4o', 'o3-mini'],
  anthropic: ['claude-3-5-haiku-20241022', 'claude-sonnet-4-20250514'],
  groq: ['llama-3.3-70b-versatile', 'mixtral-8x7b-32768'],
  gemini: ['gemini-2.0-flash', 'gemini-2.5-pro', 'gemini-1.5-pro'],
  openrouter: OPENROUTER_MODEL_PRESETS.map((p) => p.id),
  ollama: ['llama3.2', 'mistral', 'qwen2.5'],
  mlx: MLX_MODEL_PRESETS,
};

export type MlxInferenceCatalog = {
  model?: string;
  model_short?: string;
  adapters?: { id: string; label: string; path: string; active?: boolean }[];
};

export function isOpenRouterProvider(providerId: string): boolean {
  return (providerId || '').trim().toLowerCase() === 'openrouter';
}

export function isForeignModelForMlx(modelId: string): boolean {
  const m = (modelId || '').trim().toLowerCase();
  if (!m) return true;
  if (m.startsWith('mlx-community/')) return false;
  if (m.startsWith('/') || m.startsWith('./') || m.startsWith('../')) return false;
  if (m === 'openrouter/free') return true;
  return MLX_FOREIGN_MODEL_PREFIXES.some((p) => m.startsWith(p));
}

export function defaultMlxModel(mlx?: MlxInferenceCatalog | null): string {
  const envModel = (mlx?.model || '').trim();
  if (envModel && !isForeignModelForMlx(envModel)) return envModel;
  return MLX_MODEL_PRESETS[0] || '';
}

function mlxPathBasename(path: string): string {
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean);
  return parts[parts.length - 1] || path;
}

export function mlxInferenceModelPaths(mlx?: MlxInferenceCatalog | null): string[] {
  if (!mlx) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  const add = (value?: string) => {
    const v = (value || '').trim();
    if (!v || seen.has(v) || isForeignModelForMlx(v)) return;
    seen.add(v);
    out.push(v);
  };
  add(mlx.model);
  for (const adapter of mlx.adapters ?? []) add(adapter.path);
  return out;
}

export function modelLabelForOption(
  providerId: string,
  modelId: string,
  mlxCatalog?: MlxInferenceCatalog | null
): string {
  const pid = (providerId || '').trim().toLowerCase();
  const mid = (modelId || '').trim();
  if (!mid) return '—';
  if (pid === 'openrouter') {
    return OPENROUTER_LABEL_BY_ID[mid] ?? mid;
  }
  if (pid === 'mlx') {
    const adapter = (mlxCatalog?.adapters ?? []).find((a) => a.path === mid);
    if (adapter?.label) return adapter.label;
    if (mid.includes('/') && !mid.includes('mlx-community')) {
      return `${mlxPathBasename(mid)} (LoRA)`;
    }
    if (mlxCatalog?.model_short && mid === mlxCatalog.model) {
      return `${mlxCatalog.model_short} (base PM2)`;
    }
    const short = mlxPathBasename(mid);
    if (short.includes('Qwen')) return `Qwen · ${short}`;
    if (short.includes('Llama')) return `Llama · ${short}`;
    if (short.includes('gemma')) return `Gemma · ${short}`;
  }
  return mid;
}

export function modelOptionsForProvider(
  providerId: string,
  catalogModelExample?: string,
  currentModel?: string,
  extraModels?: string[]
): string[] {
  const pid = (providerId || '').trim().toLowerCase();
  const seen = new Set<string>();
  const out: string[] = [];
  const add = (m: string) => {
    const v = (m || '').trim();
    if (!v || seen.has(v)) return;
    if (pid === 'mlx' && isForeignModelForMlx(v)) return;
    seen.add(v);
    out.push(v);
  };
  const current = (currentModel || '').trim();
  if (current && !(pid === 'mlx' && isForeignModelForMlx(current))) add(current);
  for (const m of extraModels ?? []) add(m);
  for (const m of LLM_MODEL_PRESETS[pid] ?? []) add(m);
  const example = (catalogModelExample || '').trim();
  if (example) add(example);
  return out;
}

/** Modelo efectivo para UI: si el gateway no trae model, usa el primer preset del proveedor. */
export function effectiveLlmModelId(
  providerId: string,
  modelId: string,
  catalogModelExample?: string,
  mlxCatalog?: MlxInferenceCatalog | null
): string {
  const pid = (providerId || '').trim().toLowerCase();
  const mid = (modelId || '').trim();
  if (pid === 'mlx' && isForeignModelForMlx(mid)) {
    return defaultMlxModel(mlxCatalog);
  }
  if (mid) return mid;
  const options = modelOptionsForProvider(
    pid,
    catalogModelExample,
    '',
    pid === 'mlx' ? mlxInferenceModelPaths(mlxCatalog) : undefined
  );
  return options[0] || '';
}
