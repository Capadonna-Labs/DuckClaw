import { adminFetch } from './http';

export interface MessageChannel {
  id: string;
  kind: 'dm' | 'group';
  name: string;
  members: string[];
  updated_at?: string;
  last_message_preview?: string;
  message_count?: number;
}

export interface ChannelMessage {
  id: string;
  author_email: string;
  author: string;
  agent: boolean;
  body: string;
  created_at: string;
  mine: boolean;
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

export const messagesApi = {
  people: () => adminFetch<{ people: { email: string; name: string }[] }>('/messages/people').then((r) => r.people),
  channels: () => adminFetch<{ channels: MessageChannel[]; me: string }>('/messages/channels'),
  createChannel: (body: { kind: 'dm' | 'group'; name?: string; members: string[] }) =>
    adminFetch<{ ok: boolean; channel_id: string; existing?: boolean }>('/messages/channels', json('POST', body)),
  read: (id: string) =>
    adminFetch<MessageChannel & { messages: ChannelMessage[] }>(`/messages/channels/${encodeURIComponent(id)}`),
  post: (id: string, body: string) =>
    adminFetch<{ ok: boolean; message_id: string }>(`/messages/channels/${encodeURIComponent(id)}`, json('POST', { body })),
};
