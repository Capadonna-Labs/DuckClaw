'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from '@tanstack/react-table';
import { ChevronDown, ChevronRight, Database, Loader2, Play, Table2 } from 'lucide-react';
import { adminService } from '@/services/adminService';
import type { DuckdbTableCatalog } from '@/services/adminService';

type Props = {
  vaultPath: string;
};

function quoteIdent(schema: string, table: string): string {
  const q = (s: string) => `"${s.replace(/"/g, '""')}"`;
  return `${q(schema)}.${q(table)}`;
}

export function TableExplorer({ vaultPath }: Props) {
  const [schemas, setSchemas] = useState<Record<string, string[]>>({});
  const [openSchemas, setOpenSchemas] = useState<Set<string>>(new Set(['main']));
  const [sql, setSql] = useState('');
  const [columns, setColumns] = useState<string[]>([]);
  const [rows, setRows] = useState<unknown[][]>([]);
  const [loading, setLoading] = useState(false);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [catalogMeta, setCatalogMeta] = useState<DuckdbTableCatalog | null>(null);

  const loadCatalog = useCallback(async () => {
    setCatalogLoading(true);
    setError(null);
    try {
      const data = await adminService.getDuckdbTables(vaultPath || undefined);
      setSchemas(data.schemas || {});
      setCatalogMeta(data);
      setOpenSchemas(new Set(Object.keys(data.schemas || {})));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error cargando tablas');
    } finally {
      setCatalogLoading(false);
    }
  }, [vaultPath]);

  const runQuery = useCallback(
    async (query: string) => {
      if (!query.trim()) return;
      setLoading(true);
      setError(null);
      setSql(query);
      try {
        const data = await adminService.runDuckdbQuery({
          query,
          vault_path: vaultPath || undefined,
        });
        setColumns(data.columns);
        setRows(data.rows);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Error SQL');
        setColumns([]);
        setRows([]);
      } finally {
        setLoading(false);
      }
    },
    [vaultPath]
  );

  useEffect(() => {
    void loadCatalog();
  }, [loadCatalog]);

  const tableColumns = useMemo<ColumnDef<Record<string, unknown>>[]>(() => {
    return columns.map((col) => ({
      accessorKey: col,
      header: col,
      cell: (info) => {
        const v = info.getValue();
        if (v === null || v === undefined) return '—';
        if (typeof v === 'object') return JSON.stringify(v);
        return String(v);
      },
    }));
  }, [columns]);

  const tableData = useMemo(
    () => rows.map((row) => Object.fromEntries(columns.map((c, i) => [c, row[i]]))),
    [rows, columns]
  );

  const table = useReactTable({
    data: tableData,
    columns: tableColumns,
    getCoreRowModel: getCoreRowModel(),
  });

  const onTableClick = (schema: string, table: string) => {
    const q = `SELECT * FROM ${quoteIdent(schema, table)} LIMIT 100`;
    void runQuery(q);
  };

  return (
    <div className="flex flex-col gap-3 h-[calc(100vh-220px)] min-h-[420px]">
      <div className="grid gap-2 rounded-2xl border border-slate-800 bg-slate-950 px-4 py-3 text-xs text-slate-300 md:grid-cols-4">
        <SessionMetric label="BD de sesión" value={shortPath(catalogMeta?.vault_path || vaultPath)} />
        <SessionMetric label="Usuario vault" value={catalogMeta?.vault_user_id || '—'} />
        <SessionMetric label="Tenant" value={catalogMeta?.tenant_id || '—'} />
        <SessionMetric label="Tablas visibles" value={String(catalogMeta?.table_count ?? countTables(schemas))} />
      </div>

      <div className="flex gap-2">
        <input
          value={sql}
          onChange={(e) => setSql(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void runQuery(sql);
          }}
          placeholder="SELECT … (Ctrl+Enter para ejecutar)"
          className="flex-1 font-mono text-xs px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-slate-100"
        />
        <button
          type="button"
          onClick={() => void runQuery(sql)}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gov-blue-700 text-white text-sm font-bold disabled:opacity-50"
        >
          {loading ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
          Run Query
        </button>
      </div>

      {error && (
        <p className="text-sm text-red-400 bg-red-950/40 border border-red-900/50 rounded-xl px-3 py-2">
          {error}
        </p>
      )}

      <div className="flex flex-1 min-h-0 gap-3 rounded-xl border border-slate-800 overflow-hidden bg-slate-950">
        <aside className="w-[25%] min-w-[180px] max-w-[280px] border-r border-slate-800 overflow-y-auto p-2">
          {catalogLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="animate-spin text-slate-500" size={24} />
            </div>
          ) : (
            Object.entries(schemas).map(([schema, tables]) => {
              const open = openSchemas.has(schema);
              return (
                <div key={schema} className="mb-1">
                  <button
                    type="button"
                    onClick={() => {
                      setOpenSchemas((prev) => {
                        const next = new Set(prev);
                        if (next.has(schema)) next.delete(schema);
                        else next.add(schema);
                        return next;
                      });
                    }}
                    className="flex items-center gap-1 w-full px-2 py-1.5 text-left text-xs font-bold text-slate-300 hover:bg-slate-900 rounded-lg"
                  >
                    {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    <Database size={14} className="text-slate-500" />
                    {schema}
                  </button>
                  {open &&
                    tables.map((tbl) => (
                      <button
                        key={`${schema}.${tbl}`}
                        type="button"
                        onClick={() => onTableClick(schema, tbl)}
                        className="flex items-center gap-1 w-full pl-7 pr-2 py-1 text-left text-[11px] font-mono text-slate-400 hover:bg-slate-900 hover:text-slate-200 rounded-lg"
                      >
                        <Table2 size={12} />
                        {tbl}
                      </button>
                    ))}
                </div>
              );
            })
          )}
        </aside>

        <div className="flex-1 min-w-0 overflow-auto">
          {loading && rows.length === 0 ? (
            <div className="flex justify-center items-center h-full">
              <Loader2 className="animate-spin text-slate-500" size={32} />
            </div>
          ) : rows.length === 0 ? (
            <p className="text-slate-500 text-sm p-6">Selecciona una tabla o ejecuta SQL.</p>
          ) : (
            <table className="w-full text-xs border-collapse">
              <thead className="sticky top-0 bg-slate-900 z-10">
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id}>
                    {hg.headers.map((h) => (
                      <th
                        key={h.id}
                        className="text-left px-3 py-2 border-b border-slate-800 text-slate-300 font-bold whitespace-nowrap"
                      >
                        {flexRender(h.column.columnDef.header, h.getContext())}
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody>
                {table.getRowModel().rows.map((row) => (
                  <tr key={row.id} className="hover:bg-slate-900/80">
                    {row.getVisibleCells().map((cell) => (
                      <td
                        key={cell.id}
                        className="px-3 py-1.5 border-b border-slate-800/80 text-slate-200 font-mono whitespace-nowrap max-w-[320px] truncate"
                        title={String(cell.getValue() ?? '')}
                      >
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

function countTables(schemas: Record<string, string[]>): number {
  return Object.values(schemas).reduce((acc, tables) => acc + tables.length, 0);
}

function shortPath(path: string): string {
  if (!path) return '—';
  const marker = '/db/';
  const idx = path.indexOf(marker);
  if (idx >= 0) return path.slice(idx + 1);
  return path;
}

function SessionMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-[10px] font-black uppercase tracking-wide text-slate-500">{label}</p>
      <p className="truncate font-mono text-slate-100" title={value}>
        {value}
      </p>
    </div>
  );
}
