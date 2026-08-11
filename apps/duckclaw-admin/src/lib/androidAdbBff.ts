import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);

export type AndroidDeviceStatus = {
  ok: boolean;
  adb_available: boolean;
  adb_connected: boolean;
  adb_host: string;
  mcp_url: string;
  mcp_reachable: boolean;
  mcp_error?: string;
  device?: { serial?: string; state?: string; model?: string } | null;
  devices: { serial: string; state: string; model?: string }[];
  battery: { level_pct?: number; charging?: boolean };
  read_at: string;
  adb_stderr?: string;
};

function androidMcpPort(): number {
  const raw = (process.env.ANDROID_MCP_PORT || '8080').trim();
  const n = parseInt(raw, 10);
  return Number.isFinite(n) ? Math.max(1, Math.min(65535, n)) : 8080;
}

function parseAdbDevices(output: string) {
  const devices: AndroidDeviceStatus['devices'] = [];
  for (const line of output.split(/\r?\n/).slice(1)) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const parts = trimmed.split(/\s+/);
    if (parts.length < 2) continue;
    let model = '';
    for (const part of parts.slice(2)) {
      if (part.startsWith('model:')) model = part.split(':')[1] || '';
    }
    devices.push({ serial: parts[0], state: parts[1], model });
  }
  return devices;
}

function parseBattery(output: string): AndroidDeviceStatus['battery'] {
  const battery: AndroidDeviceStatus['battery'] = {};
  for (const line of output.split(/\r?\n/)) {
    const text = line.trim();
    if (text.startsWith('level:')) {
      const level = parseInt(text.split(':')[1]?.trim() || '', 10);
      if (Number.isFinite(level)) battery.level_pct = level;
    }
    if (text.startsWith('status:')) {
      const status = text.split(':')[1]?.trim();
      battery.charging = status === '2' || status === '5';
    }
  }
  return battery;
}

async function runAdb(args: string[]): Promise<{ code: number; stdout: string; stderr: string }> {
  try {
    const { stdout, stderr } = await execFileAsync('adb', args, { timeout: 15_000 });
    return { code: 0, stdout: stdout || '', stderr: stderr || '' };
  } catch (err: unknown) {
    const e = err as { code?: number; stdout?: string; stderr?: string; message?: string };
    if (e.code === 'ENOENT') return { code: 127, stdout: '', stderr: 'adb not found in PATH' };
    return {
      code: typeof e.code === 'number' ? e.code : 1,
      stdout: e.stdout || '',
      stderr: e.stderr || e.message || 'adb failed',
    };
  }
}

async function probeMcp(url: string): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fetch(url, { cache: 'no-store', signal: AbortSignal.timeout(3000) });
    if (res.ok || res.status === 404 || res.status === 405 || res.status === 406) {
      return { ok: true };
    }
    return { ok: false, error: `MCP HTTP ${res.status}` };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : 'MCP unreachable' };
  }
}

export async function androidAdbConnectLocal(): Promise<{
  ok: boolean;
  host?: string;
  error?: string;
  stdout?: string;
  stderr?: string;
}> {
  let target = (process.env.ANDROID_ADB_HOST || '').trim();
  if (!target) return { ok: false, error: 'ANDROID_ADB_HOST no configurado' };
  if (!/:\d+$/.test(target)) target = `${target}:5555`;
  const out = await runAdb(['connect', target]);
  const merged = `${out.stdout}\n${out.stderr}`.toLowerCase();
  const ok = out.code === 0 && (merged.includes('connected') || merged.includes('already connected'));
  return {
    ok,
    host: target,
    stdout: out.stdout.trim(),
    stderr: out.stderr.trim(),
    error: ok ? undefined : out.stderr.trim() || 'adb connect failed',
  };
}

export async function androidDeviceStatusLocal(): Promise<AndroidDeviceStatus> {
  const read_at = new Date().toISOString();
  const adb_host = (process.env.ANDROID_ADB_HOST || '').trim();
  const mcp_url = `http://127.0.0.1:${androidMcpPort()}/mcp`;
  const mcp = await probeMcp(mcp_url);

  const listed = await runAdb(['devices', '-l']);
  const adb_available = listed.code !== 127;
  const devices = adb_available ? parseAdbDevices(listed.stdout) : [];
  const online = devices.filter((d) => d.state === 'device');
  const primary = online[0] ?? devices[0] ?? null;

  let battery: AndroidDeviceStatus['battery'] = {};
  if (primary?.serial) {
    const bat = await runAdb(['-s', primary.serial, 'shell', 'dumpsys', 'battery']);
    if (bat.code === 0) battery = parseBattery(bat.stdout);
  }

  const adb_connected = online.length > 0;
  return {
    ok: adb_connected && mcp.ok,
    adb_available,
    adb_connected,
    adb_host,
    mcp_url,
    mcp_reachable: mcp.ok,
    mcp_error: mcp.ok ? '' : mcp.error,
    device: primary,
    devices,
    battery,
    read_at,
    adb_stderr: adb_available && listed.code !== 0 ? listed.stderr.trim() : '',
  };
}
