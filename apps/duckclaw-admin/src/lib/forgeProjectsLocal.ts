import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'fs';
import { join } from 'path';
import { repoRoot } from '@/lib/localOps';

export type ForgeProjectRow = {
  id: string;
  slug: string;
  display_name: string;
  coordinator?: string | null;
  members: string[];
  shared_vault_id?: string | null;
  path: string;
  source?: 'disk' | 'env';
  shared_context?: string;
};

function projectsDir(): string {
  return join(repoRoot(), 'packages/agents/src/duckclaw/forge/projects');
}

function splitCsv(raw: string): string[] {
  return raw.split(',').map((s) => s.trim()).filter(Boolean);
}

function parseSimpleYaml(text: string): Record<string, unknown> {
  const data: Record<string, unknown> = {};
  let listKey: string | null = null;
  for (const line of text.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const listItem = trimmed.match(/^- (.+)$/);
    if (listItem && listKey) {
      const arr = (data[listKey] as string[]) || [];
      arr.push(listItem[1].trim());
      data[listKey] = arr;
      continue;
    }
    const kv = trimmed.match(/^([a-z_]+):\s*(.*)$/i);
    if (!kv) continue;
    const [, key, rawVal] = kv;
    if (rawVal === '' || rawVal === null) {
      listKey = key;
      data[key] = [];
      continue;
    }
    listKey = null;
    data[key] = rawVal.replace(/^["']|["']$/g, '');
  }
  return data;
}

function emitProjectYaml(data: {
  id: string;
  display_name: string;
  coordinator?: string | null;
  members: string[];
  shared_vault_id?: string | null;
}): string {
  const lines = [
    `id: ${data.id}`,
    `display_name: ${JSON.stringify(data.display_name)}`,
  ];
  if (data.coordinator) lines.push(`coordinator: ${data.coordinator}`);
  lines.push('members:');
  for (const m of data.members) {
    lines.push(`  - ${m}`);
  }
  if (data.shared_vault_id) lines.push(`shared_vault_id: ${data.shared_vault_id}`);
  lines.push('shared_context_file: ./_shared/context.md');
  return `${lines.join('\n')}\n`;
}

/** Equipo definido en .env (sin nombres de plantillas en el repositorio). */
export function loadTeamFromEnv(): ForgeProjectRow | null {
  const membersRaw = (process.env.DUCKCLAW_TEAM_MEMBERS || '').trim();
  const members = splitCsv(membersRaw);
  if (!members.length) return null;

  const root = repoRoot();
  const teamId = (process.env.DUCKCLAW_TEAM_ID || 'team').trim().toLowerCase() || 'team';
  const display = (process.env.DUCKCLAW_TEAM_DISPLAY_NAME || teamId).trim();
  const coordinator = (process.env.DUCKCLAW_TEAM_COORDINATOR || '').trim() || null;
  const vault = (process.env.DUCKCLAW_TEAM_VAULT_ID || '').trim() || null;
  const ctxFile = (process.env.DUCKCLAW_TEAM_SHARED_CONTEXT_FILE || '').trim();
  let shared_context = process.env.DUCKCLAW_TEAM_SHARED_CONTEXT || '';
  if (!shared_context && ctxFile) {
    const p = ctxFile.startsWith('/') ? ctxFile : join(root, ctxFile);
    if (existsSync(p)) shared_context = readFileSync(p, 'utf-8');
  }

  return {
    id: teamId,
    slug: teamId,
    display_name: display,
    coordinator,
    members,
    shared_vault_id: vault,
    path: `forge/projects/${teamId}`,
    source: 'env',
    ...(shared_context ? { shared_context } : {}),
  };
}

export function loadEnvForgePresets(): ForgeProjectRow[] {
  const row = loadTeamFromEnv();
  return row ? [row] : [];
}

export function listForgeProjectsLocal(): ForgeProjectRow[] {
  const root = projectsDir();
  const disk: ForgeProjectRow[] = [];
  if (existsSync(root)) {
    for (const name of readdirSync(root)) {
      if (name.startsWith('.') || name.startsWith('_')) continue;
      const manifest = join(root, name, 'project.yaml');
      if (!existsSync(manifest)) continue;
      const data = parseSimpleYaml(readFileSync(manifest, 'utf-8'));
      const members = Array.isArray(data.members) ? (data.members as string[]) : [];
      disk.push({
        id: String(data.id || name),
        slug: name,
        display_name: String(data.display_name || name),
        coordinator: (data.coordinator as string) || null,
        members,
        shared_vault_id: (data.shared_vault_id as string) || null,
        path: `packages/agents/src/duckclaw/forge/projects/${name}`,
        source: 'disk',
      });
    }
  }
  const bySlug = new Map<string, ForgeProjectRow>();
  const envRow = loadTeamFromEnv();
  if (envRow) bySlug.set(envRow.slug, envRow);
  for (const row of disk) bySlug.set(row.slug, row);
  return [...bySlug.values()].sort((a, b) => a.slug.localeCompare(b.slug));
}

export function createForgeProjectLocal(body: {
  id: string;
  display_name?: string;
  members: string[];
  coordinator?: string;
  shared_vault_id?: string;
  shared_context?: string;
}): { ok: true; id: string; path: string; members: string[] } {
  const slug = body.id.replace(/[^a-zA-Z0-9_-]/g, '');
  if (!slug) throw new Error('id inválido');
  if (!body.members?.length) throw new Error('Sin miembros válidos');

  const base = join(projectsDir(), slug);
  const manifest = join(base, 'project.yaml');
  if (existsSync(manifest)) throw new Error('Proyecto ya existe');

  mkdirSync(base, { recursive: true });
  writeFileSync(
    manifest,
    emitProjectYaml({
      id: slug,
      display_name: (body.display_name || slug).trim(),
      coordinator: body.coordinator?.trim() || null,
      members: body.members,
      shared_vault_id: body.shared_vault_id?.trim() || null,
    }),
    'utf-8'
  );

  const shared = (body.shared_context || '').trim();
  if (shared) {
    const sharedDir = join(base, '_shared');
    mkdirSync(sharedDir, { recursive: true });
    writeFileSync(join(sharedDir, 'context.md'), `${shared}\n`, 'utf-8');
  }

  return {
    ok: true,
    id: slug,
    path: `packages/agents/src/duckclaw/forge/projects/${slug}`,
    members: body.members,
  };
}

export function deleteForgeProjectLocal(slug: string): void {
  const safe = slug.replace(/[^a-zA-Z0-9_-]/g, '');
  const base = join(projectsDir(), safe);
  if (!existsSync(base)) throw new Error('Proyecto no encontrado');
  rmSync(base, { recursive: true, force: true });
}
