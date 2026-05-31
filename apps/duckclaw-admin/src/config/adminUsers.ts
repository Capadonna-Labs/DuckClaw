/**
 * Dev login hints — never embed credentials in source.
 * Seed users: DUCKCLAW_ADMIN_EMAIL / DUCKCLAW_ADMIN_PASSWORD in .env.local
 */

export const DEV_LOGIN_HINT_ENABLED =
  process.env.NODE_ENV === 'development' && process.env.SHOW_DEV_HINT === 'true';

/** Optional email hint for dev UI (never password). */
export const DEV_HINT_EMAIL = (process.env.NEXT_PUBLIC_DEV_HINT_EMAIL || '').trim();
