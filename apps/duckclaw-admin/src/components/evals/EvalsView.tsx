'use client';

import { useCallback, useEffect, useState } from 'react';
import { FlaskConical } from 'lucide-react';
import { platformApi, type EvalCaseResult, type EvalReview, type EvalSuiteSummary } from '@/services/admin/platformApi';
import { ViewChrome } from '@/components/admin/embeddedView';
import SettingsSection from '@/components/settings/SettingsSection';

const STATUS_LABEL = { always_pass: 'pasa', flaky: 'inestable', always_fail: 'falla' } as const;
const STATUS_STYLE = {
  always_pass: 'text-emerald-600',
  flaky: 'text-amber-600',
  always_fail: 'text-red-600',
} as const;

const SEVERITY_LABEL = { high: 'alta', moderate: 'media', low: 'baja' } as const;
const SEVERITY_STYLE = { high: 'bg-red-100 text-red-700', moderate: 'bg-amber-100 text-amber-700', low: 'bg-gov-gray-100 text-gov-gray-600' } as const;

// What a person concluded after reading a failed case: kept between runs (the next night's run shows the same note).
function ReviewForm({ suite, id, c, onSaved }: { suite: string; id: string; c: EvalCaseResult; onSaved: () => void }) {
  const [r, setR] = useState<Omit<EvalReview, 'by' | 'ts'>>({ note: c.review?.note ?? '', possibility: c.review?.possibility ?? '', verdict: c.review?.verdict ?? '' });
  const [saving, setSaving] = useState(false);
  const save = () => {
    setSaving(true);
    platformApi
      .putEvalReview(suite, id, r)
      .then(() => setTimeout(onSaved, 1500)) // the DB-Writer applies it a moment later
      .finally(() => setSaving(false));
  };
  const field = 'mt-1 w-full rounded-lg border p-2 text-xs dark:border-dark-border dark:bg-dark-bg';
  return (
    <details className="mt-1" open={Boolean(c.review?.verdict)}>
      <summary className="cursor-pointer text-gov-gray-500">
        Revisión manual{c.review?.verdict ? `: ${c.review.verdict === 'pass' ? 'caso bien, el agente falló' : c.review.verdict === 'fail' ? 'falla real' : 'no estoy seguro'}` : ''}
      </summary>
      <label className="mt-1 block">
        Qué salió mal
        <textarea className={field} rows={2} value={r.note} onChange={(e) => setR({ ...r, note: e.target.value })} />
      </label>
      <label className="mt-1 block">
        Posibilidad (aún sin verificar)
        <textarea className={field} rows={2} value={r.possibility} onChange={(e) => setR({ ...r, possibility: e.target.value })} />
      </label>
      <div className="mt-1 flex items-center gap-2">
        <select className={field + ' !w-auto'} value={r.verdict} onChange={(e) => setR({ ...r, verdict: e.target.value as EvalReview['verdict'] })}>
          <option value="">Sin veredicto</option>
          <option value="fail">Falla real del agente</option>
          <option value="pass">El caso estaba mal</option>
          <option value="unsure">No estoy seguro</option>
        </select>
        <button type="button" disabled={saving} onClick={save} className="rounded-lg border px-2 py-1 font-bold disabled:opacity-50 dark:border-dark-border">
          {saving ? 'Guardando…' : 'Guardar'}
        </button>
        {c.review?.by && <span className="text-gov-gray-500">{c.review.by} · {c.review.ts?.slice(0, 10)}</span>}
      </div>
    </details>
  );
}

function SuiteCard({ s, onRun, onChanged }: { s: EvalSuiteSummary; onRun: (suite: string) => void; onChanged: () => void }) {
  const { latest } = s;
  const runButton = s.runnable && (
    <button
      type="button"
      disabled={s.running}
      onClick={() => onRun(s.suite)}
      className="mt-3 rounded-xl border px-3 py-1.5 text-sm font-bold disabled:opacity-50 dark:border-dark-border"
    >
      {s.running ? 'Corriendo…' : 'Correr ahora'}
    </button>
  );
  if (!latest) {
    return (
      <SettingsSection titulo={s.suite} descripcion="Aún sin corridas" icono={<FlaskConical size={22} />}>
        {runButton}
      </SettingsSection>
    );
  }
  const cases = Object.entries(latest.cases);
  // Failures first: that is what the page is for.
  const order = { always_fail: 0, flaky: 1, always_pass: 2 } as const;
  const prio = { fix_now: 0, improve_later: 1, '': 2 } as const;
  cases.sort(([, a], [, b]) => prio[a.priority ?? ''] - prio[b.priority ?? ''] || order[a.status] - order[b.status]);
  return (
    <SettingsSection
      titulo={s.suite}
      descripcion={`Última corrida ${latest.ts.slice(0, 16).replace('T', ' ')} UTC${latest.model ? ` · ${latest.model}` : ''}`}
      icono={<FlaskConical size={22} />}
    >
      {runButton}
      <p className="mt-3 text-sm">
        <b className="text-emerald-600">{latest.always_pass}</b> pasan ·{' '}
        <b className="text-amber-600">{latest.flaky}</b> inestables ·{' '}
        <b className="text-red-600">{latest.always_fail}</b> fallan de {latest.total}
      </p>
      {s.regressed.length > 0 && (
        <p className="mt-2 rounded-xl bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300">
          Regresiones desde la corrida anterior (pasaban siempre y ya no): <b>{s.regressed.join(', ')}</b>
        </p>
      )}
      {s.requirements.length > 0 && (
        <div className="mt-3 rounded-2xl border p-3 dark:border-dark-border">
          <p className="text-xs font-bold">Requisitos del agente</p>
          <ul className="mt-2 space-y-2 text-xs">
            {s.requirements.map((r) => (
              <li key={r.id}>
                <span className={r.cases.length === 0 ? 'font-bold text-amber-600' : r.failing.length ? 'font-bold text-red-600' : 'font-bold text-emerald-600'}>
                  {r.cases.length === 0 ? 'sin casos' : `${r.cases.length - r.failing.length}/${r.cases.length}`}
                </span>{' '}
                {r.text || r.id}
                {r.question && <span className="block text-gov-gray-500">Revisión: {r.question}</span>}
                {r.failing.length > 0 && <span className="block text-red-600">Fallan: {r.failing.join(', ')}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {s.by_type.length > 0 && (
        <p className="mt-3 text-xs text-gov-gray-500 dark:text-dark-muted">
          Por tipo de fallo:{' '}
          {s.by_type.map((t) => {
            const now = t.passing / Math.max(t.total, 1);
            const was = t.prev_total ? (t.prev_passing ?? 0) / t.prev_total : null;
            const arrow = was === null || now === was ? '' : now > was ? ' ▲' : ' ▼';
            return (
              <span key={t.type} className={`mr-3 whitespace-nowrap ${now < (was ?? 0) ? 'font-bold text-red-600' : ''}`}>
                {t.type || '?'} {t.passing}/{t.total}
                {arrow}
              </span>
            );
          })}
        </p>
      )}
      <div className="mt-3 flex items-end gap-1" title="Casos que pasan por corrida, de la más antigua a la más reciente">
        {[...s.history].reverse().map((h) => (
          <div
            key={h.ts}
            className={h.always_pass === h.total ? 'bg-emerald-500' : h.always_fail > 0 ? 'bg-red-500' : 'bg-amber-500'}
            style={{ width: 10, height: 6 + (28 * h.always_pass) / Math.max(h.total, 1) }}
            title={`${h.ts.slice(0, 16)} · ${h.always_pass}/${h.total}`}
          />
        ))}
      </div>
      <div className="scrollbar-thin mt-3 max-h-[50vh] overflow-auto rounded-2xl border dark:border-dark-border">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-gov-gray-50 text-left dark:bg-dark-bg">
            <tr>
              <th className="px-3 py-2 font-bold">Caso</th>
              <th className="px-3 py-2 font-bold">Tipo</th>
              <th className="px-3 py-2 font-bold">Resultado</th>
              <th className="px-3 py-2 font-bold">Por qué falla</th>
            </tr>
          </thead>
          <tbody>
            {cases.map(([id, c]) => (
              <tr key={id} className="border-t align-top dark:border-dark-border">
                <td className="px-3 py-2 font-mono text-xs">
                  {id}
                  <span className="mt-1 flex flex-wrap gap-1 font-sans">
                    {c.severity && <span className={`rounded px-1.5 py-0.5 ${SEVERITY_STYLE[c.severity]}`}>gravedad {SEVERITY_LABEL[c.severity]}</span>}
                    {c.category && <span className="rounded bg-gov-gray-100 px-1.5 py-0.5 text-gov-gray-600">{c.category}</span>}
                    {c.priority === 'fix_now' && <span className="rounded bg-red-600 px-1.5 py-0.5 font-bold text-white">arreglar ya</span>}
                  </span>
                </td>
                <td className="px-3 py-2 text-xs">{c.type}</td>
                <td className={`whitespace-nowrap px-3 py-2 text-xs font-bold ${STATUS_STYLE[c.status]}`}>
                  {STATUS_LABEL[c.status]} {c.passes}/{c.n}
                </td>
                <td className="break-words px-3 py-2 text-xs">
                  {c.failures.join('; ')}
                  {c.unverified && (
                    <span className="block text-gov-gray-500" title="Un subagente corrió herramientas que el runner no ve: «no llamó X» no se puede juzgar">
                      ⚠ parcialmente verificable (ejecutó un subagente)
                    </span>
                  )}
                  {c.status !== 'always_pass' && <ReviewForm key={`${id}-${c.review?.ts ?? ''}`} suite={s.suite} id={id} c={c} onSaved={onChanged} />}
                  {c.sample && (
                    <details className="mt-1">
                      <summary className="cursor-pointer text-gov-gray-500">Qué hizo el agente</summary>
                      {c.sample.spans?.length ? (
                        <ol className="mt-1 list-decimal space-y-1 pl-4 font-mono">
                          {c.sample.spans.map((sp, i) => (
                            <li key={i} className="break-all">
                              <b>{sp.name}</b> {sp.input}
                              <br />
                              <span className="text-gov-gray-500">→ {sp.output}</span>
                            </li>
                          ))}
                        </ol>
                      ) : (
                        <p className="mt-1 font-mono">Herramientas: {c.sample.tools.join(' → ') || '(ninguna)'}</p>
                      )}
                      <p className="mt-1 whitespace-pre-wrap font-mono">{c.sample.reply}</p>
                    </details>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SettingsSection>
  );
}

export default function EvalsView() {
  const [suites, setSuites] = useState<EvalSuiteSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    platformApi
      .getEvalRuns()
      .then((r) => setSuites(r.suites ?? []))
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, []);

  useEffect(load, [load]);

  // While a suite runs, poll: the new run shows up when its job records it.
  const anyRunning = suites?.some((s) => s.running);
  useEffect(() => {
    if (!anyRunning) return;
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [anyRunning, load]);

  const run = (suite: string) =>
    platformApi
      .runEvalSuite(suite)
      .then(load)
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));

  return (
    <ViewChrome>
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">Evals</h1>
        <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
          Baterías de casos reales que se repiten tras cada cambio de prompt, modelo o herramienta. Cada corrida se registra con{' '}
          <code className="text-xs">duckclaw.evals.golden_suite.record_run</code>.
        </p>
      </header>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {suites && suites.length === 0 && (
        <p className="py-8 text-center text-sm text-gov-gray-500">
          Aún no hay corridas. Al terminar una batería, llama a <code>record_run(suite, run)</code> y aparecerá aquí.
        </p>
      )}
      {suites?.map((s) => <SuiteCard key={s.suite} s={s} onRun={run} onChanged={load} />)}
    </ViewChrome>
  );
}
