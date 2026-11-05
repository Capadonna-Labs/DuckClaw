'use client';

import { useEffect, useState } from 'react';
import { FlaskConical } from 'lucide-react';
import { platformApi, type EvalSuiteSummary } from '@/services/admin/platformApi';
import { ViewChrome } from '@/components/admin/embeddedView';
import SettingsSection from '@/components/settings/SettingsSection';

const STATUS_LABEL = { always_pass: 'pasa', flaky: 'inestable', always_fail: 'falla' } as const;
const STATUS_STYLE = {
  always_pass: 'text-emerald-600',
  flaky: 'text-amber-600',
  always_fail: 'text-red-600',
} as const;

function SuiteCard({ s }: { s: EvalSuiteSummary }) {
  const { latest } = s;
  const cases = Object.entries(latest.cases);
  // Failures first: that is what the page is for.
  const order = { always_fail: 0, flaky: 1, always_pass: 2 } as const;
  cases.sort(([, a], [, b]) => order[a.status] - order[b.status]);
  return (
    <SettingsSection
      titulo={s.suite}
      descripcion={`Última corrida ${latest.ts.slice(0, 16).replace('T', ' ')} UTC${latest.model ? ` · ${latest.model}` : ''}`}
      icono={<FlaskConical size={22} />}
    >
      <p className="text-sm">
        <b className="text-emerald-600">{latest.always_pass}</b> pasan ·{' '}
        <b className="text-amber-600">{latest.flaky}</b> inestables ·{' '}
        <b className="text-red-600">{latest.always_fail}</b> fallan de {latest.total}
      </p>
      {s.regressed.length > 0 && (
        <p className="mt-2 rounded-xl bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300">
          Regresiones desde la corrida anterior (pasaban siempre y ya no): <b>{s.regressed.join(', ')}</b>
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
                <td className="px-3 py-2 font-mono text-xs">{id}</td>
                <td className="px-3 py-2 text-xs">{c.type}</td>
                <td className={`whitespace-nowrap px-3 py-2 text-xs font-bold ${STATUS_STYLE[c.status]}`}>
                  {STATUS_LABEL[c.status]} {c.passes}/{c.n}
                </td>
                <td className="break-words px-3 py-2 text-xs">{c.failures.join('; ')}</td>
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

  useEffect(() => {
    platformApi
      .getEvalRuns()
      .then((r) => setSuites(r.suites ?? []))
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, []);

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
      {suites?.map((s) => <SuiteCard key={s.suite} s={s} />)}
    </ViewChrome>
  );
}
