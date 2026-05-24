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

/** Modelos sugeridos por proveedor (complementa model_example del catálogo). */
export const LLM_MODEL_PRESETS: Record<string, string[]> = {
  deepseek: ['deepseek-chat', 'deepseek-reasoner'],
  openai: ['gpt-4o-mini', 'gpt-4o', 'o3-mini'],
  anthropic: ['claude-3-5-haiku-20241022', 'claude-sonnet-4-20250514'],
  groq: ['llama-3.3-70b-versatile', 'mixtral-8x7b-32768'],
  gemini: ['gemini-2.0-flash', 'gemini-2.5-pro', 'gemini-1.5-pro'],
  openrouter: [
    'anthropic/claude-sonnet-4-5',
    'google/gemini-2.5-pro',
    'openai/gpt-4o-mini',
    'deepseek/deepseek-chat',
  ],
  ollama: ['llama3.2', 'mistral', 'qwen2.5'],
  mlx: [],
};

export function modelOptionsForProvider(
  providerId: string,
  catalogModelExample?: string,
  currentModel?: string
): string[] {
  const pid = (providerId || '').trim().toLowerCase();
  const seen = new Set<string>();
  const out: string[] = [];
  const add = (m: string) => {
    const v = (m || '').trim();
    if (!v || seen.has(v)) return;
    seen.add(v);
    out.push(v);
  };
  add((currentModel || '').trim());
  for (const m of LLM_MODEL_PRESETS[pid] ?? []) add(m);
  const example = (catalogModelExample || '').trim();
  if (example && !example.includes('/')) {
    add(example);
  } else if (example) {
    add(example);
  }
  return out;
}
