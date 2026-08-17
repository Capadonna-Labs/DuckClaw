/** Resolve provider API-key documentation URLs for Integraciones. */

const DOCS_BY_INTEGRATION_ID: Record<string, string> = {
  deepseek: 'https://platform.deepseek.com/api_keys',
  groq: 'https://console.groq.com/keys',
  openai: 'https://platform.openai.com/api-keys',
  anthropic: 'https://console.anthropic.com/settings/keys',
  openrouter: 'https://openrouter.ai/keys',
  google: 'https://aistudio.google.com/apikey',
  huggingface: 'https://huggingface.co/settings/tokens',
  tavily: 'https://app.tavily.com/home',
  openweather: 'https://home.openweathermap.org/api_keys',
  fal: 'https://fal.ai/dashboard/keys',
  higgsfield: 'https://higgsfield.ai',
  github: 'https://github.com/settings/tokens',
};

export function resolveIntegrationDocsUrl(item: {
  id?: string | null;
  docs_url?: string | null;
  setting_key?: string | null;
}): string | null {
  const fromApi = (item.docs_url || '').trim();
  if (/^https?:\/\//i.test(fromApi)) return fromApi;

  const id = (item.id || '').trim().toLowerCase().replace(/-/g, '_');
  if (id && DOCS_BY_INTEGRATION_ID[id]) return DOCS_BY_INTEGRATION_ID[id];

  const key = (item.setting_key || '').trim().toLowerCase();
  const prefix = key.split('.')[0] || '';
  if (prefix && DOCS_BY_INTEGRATION_ID[prefix]) return DOCS_BY_INTEGRATION_ID[prefix];

  return null;
}
