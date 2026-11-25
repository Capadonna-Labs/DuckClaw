import { adminFetch } from './http';

export interface Contact {
  id: string;
  role: 'host' | 'guest';
  instance: string;
  email: string;
  name: string;
  created_at: string;
  agents: string[];
}

export const contactsApi = {
  list: () => adminFetch<{ contacts: Contact[]; can_invite: boolean }>('/contacts'),
  invite: () => adminFetch<{ ok: boolean; code: string; expires_at: string }>('/contacts/invite', { method: 'POST' }),
  accept: (code: string) =>
    adminFetch<{ ok: boolean; contact_id: string; name: string }>('/contacts/accept', { method: 'POST', body: JSON.stringify({ code }) }),
  remove: (id: string) => adminFetch<{ ok: boolean }>(`/contacts/${encodeURIComponent(id)}`, { method: 'DELETE' }),
};
