export type ReportsTab = 'word' | 'html';

export function parseDeliverable(raw: string | null): ReportsTab {
  return raw === 'html' ? 'html' : 'word';
}
