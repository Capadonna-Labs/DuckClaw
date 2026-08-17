/** Shared URL guards for opening provider docs (client + BFF). */

export function isSafeExternalHttpUrl(raw: string): boolean {
  const value = (raw || '').trim();
  if (!value) return false;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' || url.protocol === 'http:';
  } catch {
    return false;
  }
}
