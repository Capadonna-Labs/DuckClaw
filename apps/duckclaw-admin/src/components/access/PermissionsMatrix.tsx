'use client';

const ROWS = [
  { capability: 'Login consola', admin: true, viewer: true },
  { capability: 'Lectura (templates, DuckDB, historial)', admin: true, viewer: true },
  { capability: 'Escritura (env, workers, runtime)', admin: true, viewer: false },
  { capability: 'Gestión usuarios / grants', admin: true, viewer: false },
  { capability: 'Ops / auditoría', admin: true, viewer: false },
];

export function PermissionsMatrix() {
  return (
    <aside className="rounded-2xl border dark:border-dark-border p-4 bg-gov-gray-50 dark:bg-dark-bg">
      <h2 className="text-sm font-bold uppercase text-gov-gray-500 mb-3">Matriz consola</h2>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-gov-gray-500">
            <th className="pb-2">Capacidad</th>
            <th className="pb-2 w-12">admin</th>
            <th className="pb-2 w-12">viewer</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r) => (
            <tr key={r.capability} className="border-t dark:border-dark-border">
              <td className="py-2 pr-2">{r.capability}</td>
              <td className="py-2">{r.admin ? '✓' : '—'}</td>
              <td className="py-2">{r.viewer ? '✓' : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-[10px] text-gov-gray-500 mt-3">
        Telegram: roles <code className="font-mono">admin</code> / <code className="font-mono">user</code>.
        Grants shared: claves <code className="font-mono">default</code>, <code className="font-mono">*</code> u otras.
      </p>
    </aside>
  );
}
