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

// Names are unique across the adminService facade, which spreads every *Api module (a bare `list` overrode cronsApi.list).
export const contactsApi = {
  listContacts: () => adminFetch<{ contacts: Contact[]; can_invite: boolean }>('/contacts'),
  inviteContact: () => adminFetch<{ ok: boolean; code: string; expires_at: string }>('/contacts/invite', { method: 'POST' }),
  acceptContact: (code: string) =>
    adminFetch<{ ok: boolean; contact_id: string; name: string }>('/contacts/accept', { method: 'POST', body: JSON.stringify({ code }) }),
  removeContact: (id: string) => adminFetch<{ ok: boolean }>(`/contacts/${encodeURIComponent(id)}`, { method: 'DELETE' }),
};
