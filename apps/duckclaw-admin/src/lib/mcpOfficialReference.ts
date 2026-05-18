/** Tipos y loader del catálogo oficial (paridad con config/mcp_official_reference.yaml). */

import { existsSync, readFileSync } from 'fs';
import { join } from 'path';

function repoRoot(): string {
  const fromEnv = process.env.DUCKCLAW_REPO_ROOT?.trim();
  if (fromEnv) return fromEnv;
  return join(process.cwd(), '..', '..');
}

export type OfficialMcpServer = {
  id: string;
  name: string;
  description: string;
  runtime: string;
  install: string;
  repo_path: string;
};

export type OfficialMcpReference = {
  source_repo: string;
  source_label: string;
  registry_url: string;
  servers: OfficialMcpServer[];
};

const DEFAULT_REFERENCE: OfficialMcpReference = {
  source_repo: 'https://github.com/modelcontextprotocol/servers',
  source_label: 'modelcontextprotocol/servers',
  registry_url: 'https://registry.modelcontextprotocol.io/',
  servers: [],
};

function parseScalar(line: string, key: string): string {
  const re = new RegExp(`^\\s+${key}:\\s*(.+)$`);
  const m = line.match(re);
  if (!m) return '';
  let v = m[1].trim();
  if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
    v = v.slice(1, -1);
  }
  return v;
}

/** Parser mínimo para el YAML curado de referencia (sin dependencia yaml). */
export function loadOfficialMcpReferenceFromRepo(): OfficialMcpReference {
  const path = join(repoRoot(), 'config/mcp_official_reference.yaml');
  if (!existsSync(path)) return DEFAULT_REFERENCE;
  try {
    const lines = readFileSync(path, 'utf-8').split('\n');
    const out: OfficialMcpReference = { ...DEFAULT_REFERENCE, servers: [] };
    let current: Partial<OfficialMcpServer> | null = null;
    for (const line of lines) {
      if (line.startsWith('source_repo:')) {
        out.source_repo = parseScalar(line, 'source_repo') || out.source_repo;
        continue;
      }
      if (line.startsWith('source_label:')) {
        out.source_label = parseScalar(line, 'source_label') || out.source_label;
        continue;
      }
      if (line.startsWith('registry_url:')) {
        out.registry_url = parseScalar(line, 'registry_url') || out.registry_url;
        continue;
      }
      const idMatch = line.match(/^\s+-\s+id:\s+(\S+)/);
      if (idMatch) {
        if (current?.id) {
          out.servers.push(current as OfficialMcpServer);
        }
        current = { id: idMatch[1], name: '', description: '', runtime: 'npx', install: '', repo_path: '' };
        continue;
      }
      if (!current) continue;
      if (line.match(/^\s+name:/)) current.name = parseScalar(line, 'name');
      else if (line.match(/^\s+description:/)) current.description = parseScalar(line, 'description');
      else if (line.match(/^\s+runtime:/)) current.runtime = parseScalar(line, 'runtime');
      else if (line.match(/^\s+install:/)) current.install = parseScalar(line, 'install');
      else if (line.match(/^\s+repo_path:/)) current.repo_path = parseScalar(line, 'repo_path');
    }
    if (current?.id) out.servers.push(current as OfficialMcpServer);
    return out;
  } catch {
    return DEFAULT_REFERENCE;
  }
}
