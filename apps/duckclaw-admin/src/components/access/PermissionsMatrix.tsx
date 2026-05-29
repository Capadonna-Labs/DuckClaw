'use client';

const ROWS = [
  { capability: 'Login consola', admin: true, user: true },
  { capability: 'Usar chat y agente default', admin: true, user: true },
  { capability: 'Crear agentes desde plantillas', admin: true, user: true },
  { capability: 'Runtime, DuckDB y ajustes avanzados', admin: true, user: false },
  { capability: 'Gestión usuarios / grants', admin: true, user: false },
  { capability: 'Ops / auditoría', admin: true, user: false },
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
            <th className="pb-2 w-12">user</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r) => (
            <tr key={r.capability} className="border-t dark:border-dark-border">
              <td className="py-2 pr-2">{r.capability}</td>
              <td className="py-2">{r.admin ? '✓' : '—'}</td>
              <td className="py-2">{r.user ? '✓' : '—'}</td>
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
