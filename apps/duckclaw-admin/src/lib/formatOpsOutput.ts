/** Convierte salida cruda de ops/PM2 en texto legible con emojis. */

export type OpsRunResult = {
  ok?: boolean;
  exit_code: number;
  stdout?: string;
  stderr?: string;
  executed_via?: string;
  op_id?: string;
};

/** Resultado tras `normalizeOpsResult` — `ok` siempre definido. */
export type NormalizedOpsRunResult = OpsRunResult & {
  ok: boolean;
  op_id: string;
  stdout: string;
  stderr: string;
  executed_via: 'local' | string;
};

/** Ops que no deben ejecutarse vía gateway (reinician el propio gateway). */
export const HOST_ONLY_OPS = new Set([
  'pm2_restart_gateway',
  'pm2_start_gateway',
  'start_stack',
  'start_telegram_ingress',
]);

const HIGH_RESTART_WARN = 20;
const HIGH_RESTART_CRITICAL = 100;

export function isPm2RestartInterrupted(r: Pick<OpsRunResult, 'exit_code' | 'stdout' | 'op_id'>): boolean {
  if (r.exit_code !== -2) return false;
  const stdout = r.stdout ?? '';
  if (!/Applying action restartProcessId/i.test(stdout)) return false;
  if (r.op_id === 'pm2_restart_gateway') return /DuckClaw-Gateway/i.test(stdout);
  return false;
}

/** PM2 mató el proceso padre al reiniciar el gateway; la acción sí se aplicó. */
export function normalizeOpsResult(r: OpsRunResult): NormalizedOpsRunResult {
  if (isPm2RestartInterrupted(r)) {
    return {
      ...r,
      ok: true,
      exit_code: 0,
      op_id: r.op_id ?? '',
      stdout: r.stdout ?? '',
      stderr: r.stderr ?? '',
      executed_via: r.executed_via ?? 'local',
    };
  }
  return {
    ...r,
    ok: r.ok ?? r.exit_code === 0,
    op_id: r.op_id ?? '',
    stdout: r.stdout ?? '',
    stderr: r.stderr ?? '',
    executed_via: r.executed_via ?? 'local',
  };
}

export function formatOpsOutput(r: OpsRunResult): string {
  const normalized = normalizeOpsResult(r);
  const ok = normalized.ok ?? normalized.exit_code === 0;
  const lines: string[] = [];

  lines.push(ok ? '✅ Completado correctamente' : `❌ ${_exitSummary(normalized.exit_code, r.op_id)}`);

  if (isPm2RestartInterrupted(r)) {
    lines.push('ℹ️ El reinicio se aplicó; la conexión se cortó al reiniciar el gateway (normal).');
  }
  if (r.op_id === 'start_stack' && ok) {
    lines.push('ℹ️ Plataforma lista: PM2 + Tailscale/Telegram. Prueba un mensaje al bot.');
    lines.push(
      'ℹ️ Admin móvil (:8443): si la página se cortó unos segundos, recarga; el proxy Serve se re-aplicó al final.'
    );
  }
  if (r.op_id === 'start_telegram_ingress' && ok) {
    lines.push('ℹ️ Tailscale Funnel activo. Prueba un mensaje al bot en Telegram.');
  }

  if (r.executed_via === 'local') {
    lines.push('🖥️ Ejecutado en este equipo (consola del admin)');
  } else if (r.executed_via) {
    lines.push(`🌐 Ejecutado vía: ${r.executed_via}`);
  }

  const stdoutBlock = _formatStdout(r.stdout ?? '', r.op_id);
  if (stdoutBlock) lines.push('', stdoutBlock);

  const stderrBlock = _formatStderr(r.stderr ?? '');
  if (stderrBlock) lines.push('', stderrBlock);

  if (!stdoutBlock && !stderrBlock && ok) {
    lines.push('', '📭 Sin salida adicional');
  }

  return lines.join('\n').trim() || '📭 Sin salida';
}

function _exitSummary(code: number, opId?: string): string {
  if (code === 0) return 'Completado';
  if (code === -2) {
    if (opId === 'pm2_restart_gateway') {
      return 'Reinicio interrumpido o proceso no encontrado (código -2). Comprueba: pm2 list';
    }
    return 'Comando interrumpido o no encontrado (código -2)';
  }
  if (code === 1) return 'El comando terminó con error (código 1)';
  if (code === 127) return 'Comando no encontrado (código 127)';
  return `Error (código de salida: ${code})`;
}

type Pm2Row = {
  id: number;
  name: string;
  pid: string;
  uptime: string;
  restarts: number;
  status: string;
  cpu: string;
  memory: string;
};

function _parsePm2ListTable(text: string): Pm2Row[] {
  const rows: Pm2Row[] = [];
  for (const line of text.split('\n')) {
    if (!line.includes('│') || /[┌├└]/.test(line)) continue;
    const cols = line
      .split('│')
      .map((c) => c.trim())
      .filter((c) => c.length > 0);
    if (cols.length < 9) continue;
    const id = Number.parseInt(cols[0], 10);
    if (Number.isNaN(id)) continue;
    rows.push({
      id,
      name: cols[1],
      pid: cols[5] ?? '—',
      uptime: cols[6] ?? '—',
      restarts: Number.parseInt(cols[7], 10) || 0,
      status: (cols[8] ?? 'unknown').toLowerCase(),
      cpu: cols[9] ?? '—',
      memory: cols[10] ?? '—',
    });
  }
  return rows;
}

function _statusEmoji(status: string): string {
  if (status === 'online') return '🟢';
  if (status === 'stopped') return '⏹️';
  if (status === 'errored' || status === 'error') return '🔴';
  if (status === 'launching' || status === 'stopping') return '🟡';
  return '⚪';
}

function _restartLabel(count: number): string {
  const base = `🔄 Reinicios: ${count}`;
  if (count >= HIGH_RESTART_CRITICAL) return `${base} 🚨 (muy alto — revisar logs)`;
  if (count >= HIGH_RESTART_WARN) return `${base} ⚠️ (alto)`;
  return base;
}

function _formatPm2ListTable(text: string): string {
  const rows = _parsePm2ListTable(text);
  if (!rows.length) return '';

  const lines = ['📋 Procesos PM2', ''];
  for (const row of rows) {
    lines.push(`${_statusEmoji(row.status)} ${row.name}  ·  ${row.status}`);
    lines.push(`   ⏱ Uptime: ${row.uptime}  ·  ${_restartLabel(row.restarts)}`);
    lines.push(`   💾 Mem: ${row.memory}  ·  ⚡ CPU: ${row.cpu}  ·  🆔 PID: ${row.pid}`);
    lines.push('');
  }
  return lines.join('\n').trimEnd();
}

function _formatPm2RestartAction(text: string): string {
  const pm2Action = text.match(
    /\[PM2\] Applying action (\w+) on app \[([^\]]+)\]\(ids:\s*\[\s*(\d+)\s*\]\)/i
  );
  if (!pm2Action) return '';

  const [, action, app, id] = pm2Action;
  const actionLabel =
    action === 'restartProcessId'
      ? 'reinicio'
      : action === 'stopProcessId'
        ? 'detención'
        : action === 'deleteProcessId'
          ? 'eliminación'
          : action;

  const launched = /\[PM2\]\s+\[[^\]]+\]\(\d+\)\s*✓/i.test(text);
  const listBlock = _formatPm2ListTable(text);

  const lines = [
    '📤 Detalle',
    `   🔄 Acción: ${actionLabel}`,
    `   📦 Proceso: ${app}`,
    `   🆔 ID en PM2: ${id}`,
  ];
  if (launched) lines.push('   ✅ Proceso relanzado');
  if (listBlock) lines.push('', listBlock);
  return lines.join('\n');
}

function _hasAnsiCodes(text: string): boolean {
  return /\x1b\[[\d;]*m|\x9b[\d;]*m/.test(text);
}

function _formatPm2Logs(text: string): string {
  const lines = text.split('\n').filter((l) => l.trim());
  if (!lines.length) return '';
  if (_hasAnsiCodes(text)) {
    return ['📜 Últimas líneas de log (colores ANSI)', '', ...lines.slice(-40)].join('\n');
  }
  const out = ['📜 Últimas líneas de log', ''];
  for (const line of lines.slice(-40)) {
    const t = line.trim();
    if (!t) continue;
    if (/error|exception|traceback|fatal/i.test(t)) out.push(`   🔴 ${t}`);
    else if (/warn/i.test(t)) out.push(`   🟡 ${t}`);
    else if (/info|notice/i.test(t)) out.push(`   🔵 ${t}`);
    else if (/^\d+\|/.test(t)) out.push(`   🟢 ${t}`);
    else out.push(`   ${t}`);
  }
  return out.join('\n');
}

function _formatStdout(stdout: string, opId?: string): string {
  const text = stdout.trim();
  if (!text) return '';

  const listFormatted = _formatPm2ListTable(text);
  if (listFormatted && !/\[PM2\] Applying action/i.test(text)) {
    return listFormatted;
  }

  const restartBlock = _formatPm2RestartAction(text);
  if (restartBlock) return restartBlock;

  if (/\[PM2\]\s+Process\s+\w+\s+launched/i.test(text)) {
    return `🚀 ${_pm2Lines(text)}`;
  }

  if (opId?.startsWith('pm2_logs') || /^\d+\|/.test(text)) {
    const logs = _formatPm2Logs(text);
    if (logs) return logs;
  }

  if (text.includes('[PM2]')) {
    const mixed = _formatPm2ListTable(text);
    if (mixed) return mixed;
    return `📤 ${_pm2Lines(text)}`;
  }

  if (/doctor|DuckClaw|bootstrap|OK|healthy/i.test(text)) {
    return `🩺 Diagnóstico\n\n${text}`;
  }

  return `📤 Salida\n\n${text}`;
}

function _pm2Lines(text: string): string {
  return text
    .split('\n')
    .map((line) => {
      const t = line.trim();
      if (!t) return '';
      const pm2 = t.match(/\[PM2\]\s*(.+)/i);
      if (pm2) return `   ℹ️ ${pm2[1]}`;
      return `   ${t}`;
    })
    .filter(Boolean)
    .join('\n');
}

function _formatStderr(stderr: string): string {
  const text = stderr.trim();
  if (!text) return '';
  return `⚠️ Advertencias / errores\n\n${text}`;
}
