import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs';
import { join } from 'path';
import { NextRequest, NextResponse } from 'next/server';
import type { KanbanCard, KanbanStatus } from '@/lib/kanbanTypes';
import { syncKanbanCardsWithTeam } from '@/lib/kanbanSync';
import { repoRoot } from '@/lib/localOps';

const VALID: KanbanStatus[] = ['pendiente', 'en_progreso', 'completo'];

function storePath(): string {
  const dir = join(repoRoot(), '.duckclaw');
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
  return join(dir, 'admin-kanban.json');
}

function loadCards(): KanbanCard[] {
  const path = storePath();
  if (!existsSync(path)) return [];
  try {
    const raw = JSON.parse(readFileSync(path, 'utf-8'));
    return Array.isArray(raw?.cards) ? raw.cards : [];
  } catch {
    return [];
  }
}

function saveCards(cards: KanbanCard[]) {
  writeFileSync(storePath(), JSON.stringify({ cards }, null, 2), 'utf-8');
}

function newId(): string {
  return `card_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export async function GET() {
  let cards = loadCards();
  try {
    const synced = await syncKanbanCardsWithTeam(cards);
    cards = synced.cards;
    if (synced.changed) saveCards(cards);
  } catch {
    /* gateway unreachable: return local cards only */
  }
  return NextResponse.json({ cards });
}

export async function POST(req: NextRequest) {
  const role = req.headers.get('x-duckclaw-role') || 'admin';
  if (role !== 'admin') {
    return NextResponse.json({ detail: 'Solo admin' }, { status: 403 });
  }
  const body = await req.json().catch(() => ({}));
  const title = String(body.title || 'Nuevo agente').trim().slice(0, 120);
  const description = String(body.description || '').trim().slice(0, 2000);
  const status = VALID.includes(body.status) ? body.status : 'pendiente';
  const now = new Date().toISOString();
  const card: KanbanCard = {
    id: newId(),
    title,
    description,
    status,
    worker_id: body.worker_id ? String(body.worker_id) : undefined,
    tags: Array.isArray(body.tags) ? body.tags.map(String).slice(0, 8) : [],
    created_at: now,
    updated_at: now,
  };
  const cards = loadCards();
  cards.unshift(card);
  saveCards(cards);
  return NextResponse.json({ ok: true, card });
}

export async function PATCH(req: NextRequest) {
  const role = req.headers.get('x-duckclaw-role') || 'admin';
  if (role !== 'admin') {
    return NextResponse.json({ detail: 'Solo admin' }, { status: 403 });
  }
  const body = await req.json().catch(() => ({}));
  const id = String(body.id || '').trim();
  if (!id) return NextResponse.json({ detail: 'id requerido' }, { status: 400 });

  const cards = loadCards();
  const idx = cards.findIndex((c) => c.id === id);
  if (idx < 0) return NextResponse.json({ detail: 'Tarjeta no encontrada' }, { status: 404 });

  const cur = cards[idx];
  if (body.title != null) cur.title = String(body.title).trim().slice(0, 120);
  if (body.description != null) cur.description = String(body.description).trim().slice(0, 2000);
  if (body.status != null && VALID.includes(body.status)) cur.status = body.status;
  if (body.worker_id != null) cur.worker_id = String(body.worker_id) || undefined;
  cur.updated_at = new Date().toISOString();
  cards[idx] = cur;
  saveCards(cards);
  return NextResponse.json({ ok: true, card: cur });
}

export async function DELETE(req: NextRequest) {
  const role = req.headers.get('x-duckclaw-role') || 'admin';
  if (role !== 'admin') {
    return NextResponse.json({ detail: 'Solo admin' }, { status: 403 });
  }
  const url = new URL(req.url);
  const id = url.searchParams.get('id')?.trim();
  if (!id) return NextResponse.json({ detail: 'id requerido' }, { status: 400 });
  const cards = loadCards().filter((c) => c.id !== id);
  saveCards(cards);
  return NextResponse.json({ ok: true });
}
