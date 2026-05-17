import { existsSync, readFileSync } from 'fs';
import { join } from 'path';
import { repoRoot } from '@/lib/localOps';

export function fallbackPlaygroundConfig() {
  const envPath = join(repoRoot(), '.env');
  const values: Record<string, string> = {};
  if (existsSync(envPath)) {
    for (const line of readFileSync(envPath, 'utf-8').split('\n')) {
      const s = line.trim();
      if (!s || s.startsWith('#') || !s.includes('=')) continue;
      const k = s.split('=')[0].trim();
      if (k.startsWith('DUCKCLAW_LLM') || k.startsWith('LLM_')) {
        values[k] = '***';
      }
    }
  }
  const read = (k: string) => {
    if (!existsSync(envPath)) return '';
    for (const line of readFileSync(envPath, 'utf-8').split('\n')) {
      const s = line.trim();
      if (s.startsWith(`${k}=`)) return s.split('=').slice(1).join('=').trim().replace(/^["']|["']$/g, '');
    }
    return '';
  };
  const prov = read('DUCKCLAW_LLM_PROVIDER') || read('LLM_PROVIDER');
  const model = read('DUCKCLAW_LLM_MODEL') || read('LLM_MODEL');
  const base = read('DUCKCLAW_LLM_BASE_URL') || read('LLM_BASE_URL');
  return {
    llm: { provider: prov, model, base_url: base },
    catalog: [],
    workers: [],
    _fallback: true,
    note: 'Gateway sin /playground/config — reinicia PM2',
  };
}
