import filterSpec from '../../../../packages/shared/src/duckclaw/seeds/pm2_node_dev_env_filter_v1.json';

export type Pm2NodeDevEnvFilterSpec = typeof filterSpec;

export const PM2_NODE_DEV_ENV_FILTER = filterSpec;

export function isPm2NodeDevBlockedKey(key: string): boolean {
  if (PM2_NODE_DEV_ENV_FILTER.blocked_keys.includes(key)) return true;
  for (const prefix of PM2_NODE_DEV_ENV_FILTER.blocked_extra_prefixes) {
    if (key.startsWith(prefix)) return true;
  }
  return PM2_NODE_DEV_ENV_FILTER.blocked_prefixes.some((prefix) => key.startsWith(prefix));
}

export function isPm2NodeDevAllowedKey(key: string): boolean {
  if (PM2_NODE_DEV_ENV_FILTER.allowed_keys.includes(key)) return true;
  return PM2_NODE_DEV_ENV_FILTER.allowed_prefixes.some((prefix) => key.startsWith(prefix));
}
