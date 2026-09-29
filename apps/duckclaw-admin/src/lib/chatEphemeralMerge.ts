/** Reinserta heartbeats ephemeral en historial Redis tras reload (sessionStorage). */

import type { ChatMsg } from '@/components/chat/types';

export function countUsersBefore(messages: ChatMsg[], beforeIndex: number): number {
  let n = 0;
  const end = Math.min(beforeIndex, messages.length);
  for (let i = 0; i < end; i++) {
    if (messages[i]?.role === 'user') n += 1;
  }
  return n;
}

export function anchorText(text: string | undefined, max = 200): string {
  return (text || '').replace(/\s+/g, ' ').trim().slice(0, max);
}

/** User text + start of the reply for the turn containing ``index``. */
export function turnAnchorsAt(
  messages: ChatMsg[],
  index: number
): { anchorUser: string; anchorAssistant: string } {
  let anchorUser = '';
  for (let i = index - 1; i >= 0; i--) {
    if (messages[i]?.role === 'user') {
      anchorUser = anchorText(messages[i].text);
      break;
    }
  }
  let anchorAssistant = '';
  for (let i = index + 1; i < messages.length; i++) {
    const role = messages[i]?.role;
    if (role === 'user') break;
    if (role === 'assistant' && (messages[i].text || '').trim()) {
      anchorAssistant = anchorText(messages[i].text, 120);
      break;
    }
  }
  return { anchorUser, anchorAssistant };
}

/**
 * turnUserIndex is a position inside the capped history window (48 msgs), so
 * once a chat passes that cap it goes stale as soon as the window slides — every
 * stored tool event ended up pointing at the last turn and one "Tool usage" box
 * kept growing across turns. Re-resolve anchored events against the *current*
 * window by content; drop those whose turn has scrolled out of it.
 */
export function resolveAnchoredTurns(server: ChatMsg[], ephemeral: ChatMsg[]): ChatMsg[] {
  const turns: { ordinal: number; user: string; assistant: string }[] = [];
  let ordinal = 0;
  for (let i = 0; i < server.length; i++) {
    if (server[i]?.role !== 'user') continue;
    ordinal += 1;
    const { anchorAssistant } = turnAnchorsAt(server, i);
    turns.push({ ordinal, user: anchorText(server[i].text), assistant: anchorAssistant });
  }
  const out: ChatMsg[] = [];
  for (const e of ephemeral) {
    if (!e.anchorUser && !e.anchorAssistant) {
      out.push(e);
      continue;
    }
    const byAssistant = e.anchorAssistant
      ? turns.filter((t) => t.assistant && t.assistant === e.anchorAssistant)
      : [];
    const byUser = e.anchorUser ? turns.filter((t) => t.user === e.anchorUser) : [];
    const hit = byAssistant[byAssistant.length - 1] ?? byUser[byUser.length - 1];
    if (hit) {
      out.push({ ...e, turnUserIndex: hit.ordinal });
    } else if (!e.anchorAssistant) {
      // In-flight turn (reply not captured yet) whose user text the server stored
      // differently (e.g. attachment-only send): keep the positional fallback.
      out.push(e);
    }
    // Anchored to a finished turn that's no longer in the window: drop, don't
    // let it pile onto the last turn.
  }
  return out;
}

function bucketEphemeralByTurn(
  ephemeral: ChatMsg[],
  assistantCount: number
): Map<number, ChatMsg[]> {
  const buckets = new Map<number, ChatMsg[]>();
  const legacy: ChatMsg[] = [];

  for (const e of ephemeral) {
    const turn = e.turnUserIndex;
    if (turn == null || turn < 1) {
      legacy.push(e);
      continue;
    }
    const list = buckets.get(turn) ?? [];
    list.push(e);
    buckets.set(turn, list);
  }

  if (legacy.length && assistantCount > 0) {
    const tools = legacy.filter((e) => e.heartbeatKind === 'tool');
    const other = legacy.filter((e) => e.heartbeatKind !== 'tool');
    const chunk = Math.max(1, Math.ceil(tools.length / assistantCount));
    let offset = 0;
    for (let turn = 1; turn <= assistantCount && offset < tools.length; turn += 1) {
      const list = buckets.get(turn) ?? [];
      list.push(...tools.slice(offset, offset + chunk));
      buckets.set(turn, list);
      offset += chunk;
    }
    if (offset < tools.length) {
      const list = buckets.get(assistantCount) ?? [];
      list.push(...tools.slice(offset));
      buckets.set(assistantCount, list);
    }
    if (other.length) {
      const list = buckets.get(assistantCount) ?? [];
      list.push(...other);
      buckets.set(assistantCount, list);
    }
  } else if (legacy.length) {
    buckets.set(-1, legacy);
  }

  return buckets;
}

/** Inserta tools del turno N tras el user N (antes del assistant si existe). */
function spliceToolsForTurn(out: ChatMsg[], turn: number, tools: ChatMsg[]): void {
  if (!tools.length) return;
  let userCount = 0;
  let userIdx = -1;
  for (let i = 0; i < out.length; i++) {
    if (out[i]?.role === 'user') {
      userCount += 1;
      if (userCount === turn) {
        userIdx = i;
        break;
      }
    }
  }
  if (userIdx < 0) {
    let insertAt = out.length;
    for (let i = out.length - 1; i >= 0; i--) {
      if (out[i]?.role === 'assistant') {
        insertAt = i;
        break;
      }
    }
    out.splice(insertAt, 0, ...tools);
    return;
  }
  let insertAt = userIdx + 1;
  while (insertAt < out.length && out[insertAt]?.role === 'heartbeat') {
    insertAt += 1;
  }
  out.splice(insertAt, 0, ...tools);
}

export function interleaveEphemeralIntoHistory(
  server: ChatMsg[],
  rawEphemeral: ChatMsg[]
): ChatMsg[] {
  const ephemeral = resolveAnchoredTurns(server, rawEphemeral);
  if (!ephemeral.length) return server;

  let assistantCount = 0;
  for (const m of server) {
    if (m.role === 'assistant') assistantCount += 1;
  }

  let serverUserCount = 0;
  for (const m of server) {
    if (m.role === 'user') serverUserCount += 1;
  }

  // turn_user_index puede quedar +1 cuando Redis ya está en el techo MAX_MSGS
  // (persist trunca el par más viejo y el user nuevo sigue siendo el último).
  const buckets = bucketEphemeralByTurn(ephemeral, assistantCount);
  const orphan = buckets.get(-1) ?? [];
  buckets.delete(-1);
  if (serverUserCount > 0) {
    for (const turn of [...buckets.keys()]) {
      if (turn > serverUserCount) {
        const overflow = buckets.get(turn) ?? [];
        buckets.delete(turn);
        const list = buckets.get(serverUserCount) ?? [];
        list.push(...overflow);
        buckets.set(serverUserCount, list);
      }
    }
  }

  const out: ChatMsg[] = [];
  let userCount = 0;
  for (const m of server) {
    if (m.role === 'user') userCount += 1;
    if (m.role === 'assistant') {
      out.push(...(buckets.get(userCount) ?? []));
      buckets.delete(userCount);
    }
    out.push(m);
  }

  // Turnos sin assistant en Redis (respuesta aún no persistida): no empujar al final.
  for (const [turn, tools] of [...buckets.entries()].sort((a, b) => a[0] - b[0])) {
    spliceToolsForTurn(out, turn, tools);
  }
  if (orphan.length) {
    let insertAt = out.length;
    for (let i = out.length - 1; i >= 0; i--) {
      if (out[i]?.role === 'assistant') {
        insertAt = i;
        break;
      }
    }
    out.splice(insertAt, 0, ...orphan);
  }
  return out;
}
