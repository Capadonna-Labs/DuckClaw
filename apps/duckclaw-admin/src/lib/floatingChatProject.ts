const STORAGE_KEY = 'duckclaw-admin-last-project-id';

export function readLastProjectId(): string {
  if (typeof window === 'undefined') return '';
  try {
    return (localStorage.getItem(STORAGE_KEY) || '').trim();
  } catch {
    return '';
  }
}

export function writeLastProjectId(projectId: string): void {
  if (typeof window === 'undefined') return;
  const id = (projectId || '').trim();
  try {
    if (id) localStorage.setItem(STORAGE_KEY, id);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

export function projectIdFromPathname(pathname: string): string {
  const projectMatch = pathname.match(/^\/projects\/([^/]+)/);
  if (projectMatch?.[1]) {
    try {
      return decodeURIComponent(projectMatch[1]);
    } catch {
      return projectMatch[1];
    }
  }
  return '';
}
