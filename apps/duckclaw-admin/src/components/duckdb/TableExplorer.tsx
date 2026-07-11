'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from '@tanstack/react-table';
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Database,
  Download,
  Loader2,
  Play,
  RefreshCw,
  Table2,
} from 'lucide-react';
import { adminService } from '@/services/adminService';
import type { DuckdbTableCatalog } from '@/services/adminService';
import { downloadDuckdbCsv } from '@/lib/duckdbCsvExport';

type Props = {
  vaultPath: string;
  refreshKey?: number;
};

const PAGE_SIZE_OPTIONS = [25, 50, 100, 200, 500] as const;

function quoteIdent(schema: string, table: string): string {
  const q = (s: string) => `"${s.replace(/"/g, '""')}"`;
  return `${q(schema)}.${q(table)}`;
}

function sqlHasExplicitLimit(query: string): boolean {
  return /\blimit\s+\d+/i.test(query);
}

export function TableExplorer({ vaultPath, refreshKey = 0 }: Props) {
  const [schemas, setSchemas] = useState<Record<string, string[]>>({});
  const [openSchemas, setOpenSchemas] = useState<Set<string>>(new Set(['main']));
  const [sql, setSql] = useState('');
  const [columns, setColumns] = useState<string[]>([]);
  const [rows, setRows] = useState<unknown[][]>([]);
  const [loading, setLoading] = useState(false);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [writeOk, setWriteOk] = useState<string | null>(null);
  const [catalogMeta, setCatalogMeta] = useState<DuckdbTableCatalog | null>(null);
  const [pageSize, setPageSize] = useState<number>(100);
  const [pageIndex, setPageIndex] = useState(0);
  const [serverPaging, setServerPaging] = useState(true);
  const [resultOffset, setResultOffset] = useState(0);
  const [limitApplied, setLimitApplied] = useState<number | null>(null);
  const [hasMore, setHasMore] = useState(false);

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
    async (query: string, opts?: { page?: number; size?: number }) => {
      if (!query.trim()) return;
      const nextPage = opts?.page ?? 0;
      const nextSize = opts?.size ?? pageSize;
      const explicitLimit = sqlHasExplicitLimit(query);

      setLoading(true);
      setError(null);
      setWriteOk(null);
      setSql(query);
      setPageIndex(nextPage);

      try {
        const data = await adminService.runDuckdbQuery({
          query,
          vault_path: vaultPath || undefined,
          limit: explicitLimit ? undefined : nextSize,
          offset: explicitLimit ? undefined : nextPage * nextSize,
        });
        if (data.mode === 'write') {
          setColumns([]);
          setRows([]);
          setHasMore(false);
          setLimitApplied(null);
          setResultOffset(0);
          setWriteOk(`Escritura aplicada (task_id: ${data.task_id ?? 'ok'})`);
          void loadCatalog();
        } else {
          setColumns(data.columns);
          setRows(data.rows);
          setServerPaging(!explicitLimit);
          setLimitApplied(data.limit_applied ?? null);
          setResultOffset(data.offset ?? 0);
          setHasMore(Boolean(data.has_more));
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Error SQL');
        setColumns([]);
        setRows([]);
        setHasMore(false);
      } finally {
        setLoading(false);
      }
    },
    [vaultPath, loadCatalog, pageSize]
  );

  useEffect(() => {
    void loadCatalog();
  }, [loadCatalog, refreshKey]);

  const visibleRows = useMemo(() => {
    if (serverPaging) return rows;
    const start = pageIndex * pageSize;
    return rows.slice(start, start + pageSize);
  }, [rows, pageIndex, pageSize, serverPaging]);

  const clientPageCount = serverPaging ? 1 : Math.max(1, Math.ceil(rows.length / pageSize));
  const canPrev = pageIndex > 0;
  const canNext = serverPaging ? hasMore : pageIndex + 1 < clientPageCount;

  const rowRangeLabel = useMemo(() => {
    if (columns.length === 0 && rows.length === 0) return null;
    const count = visibleRows.length;
    if (count === 0) return '0 filas';
    const start = serverPaging ? resultOffset + 1 : pageIndex * pageSize + 1;
    const end = serverPaging ? resultOffset + count : pageIndex * pageSize + count;
    const limitHint =
      limitApplied != null ? ` · límite ${limitApplied}` : sqlHasExplicitLimit(sql) ? ' · LIMIT en SQL' : '';
    const moreHint = hasMore && serverPaging ? ' · hay más filas' : '';
    return `Filas ${start}–${end}${limitHint}${moreHint}`;
  }, [
    columns.length,
    rows.length,
    visibleRows.length,
    serverPaging,
    resultOffset,
    pageIndex,
    pageSize,
    limitApplied,
    sql,
    hasMore,
  ]);

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
    () => visibleRows.map((row) => Object.fromEntries(columns.map((c, i) => [c, row[i]]))),
    [visibleRows, columns]
  );

  const table = useReactTable({
    data: tableData,
    columns: tableColumns,
    getCoreRowModel: getCoreRowModel(),
  });

  const onTableClick = (schema: string, table: string) => {
    setPageIndex(0);
    const q = `SELECT * FROM ${quoteIdent(schema, table)}`;
    void runQuery(q, { page: 0, size: pageSize });
  };

  const goPrev = () => {
    if (!canPrev || loading || !sql.trim()) return;
    const next = pageIndex - 1;
    if (serverPaging) {
      void runQuery(sql, { page: next, size: pageSize });
    } else {
      setPageIndex(next);
    }
  };

  const goNext = () => {
    if (!canNext || loading || !sql.trim()) return;
    const next = pageIndex + 1;
    if (serverPaging) {
      void runQuery(sql, { page: next, size: pageSize });
    } else {
      setPageIndex(next);
    }
  };

  const onPageSizeChange = (nextSize: number) => {
    setPageSize(nextSize);
    if (sql.trim() && columns.length > 0) {
      void runQuery(sql, { page: 0, size: nextSize });
    } else {
      setPageIndex(0);
    }
  };

  const exportCsv = () => {
    if (columns.length === 0) return;
    const exportRows = serverPaging ? rows : visibleRows;
    downloadDuckdbCsv(`duckdb-export-${Date.now()}.csv`, columns, exportRows);
  };

  return (
    <div className="flex min-h-[480px] flex-col gap-3">
      <section className="rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gov-gray-100 px-4 py-3 dark:border-dark-border">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-gov-gray-900 dark:text-dark-text">SQL</h2>
            <p className="mt-0.5 truncate font-mono text-xs text-gov-gray-500 dark:text-dark-muted">
              {shortPath(catalogMeta?.vault_path || vaultPath)} ·{' '}
              {catalogMeta?.table_count ?? countTables(schemas)} tablas · máx 500 filas/página
            </p>
          </div>
          <button
            type="button"
            onClick={() => void loadCatalog()}
            disabled={catalogLoading}
            className="inline-flex items-center gap-1 rounded-lg border border-gov-gray-200 px-2.5 py-1.5 text-xs font-semibold dark:border-dark-border"
          >
            <RefreshCw size={12} className={catalogLoading ? 'animate-spin' : ''} />
            Catálogo
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-2 p-4">
          <input
            value={sql}
            onChange={(e) => setSql(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void runQuery(sql, { page: 0 });
            }}
            placeholder="SELECT … (Ctrl+Enter)"
            className="min-w-[200px] flex-1 rounded-lg border border-gov-gray-200 bg-gov-gray-50 px-3 py-2 font-mono text-xs dark:border-dark-border dark:bg-dark-bg"
          />
          <label className="inline-flex items-center gap-1.5 text-xs text-gov-gray-600 dark:text-dark-muted">
            Filas
            <select
              value={pageSize}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
              className="rounded-lg border border-gov-gray-200 bg-white px-2 py-1.5 font-mono dark:border-dark-border dark:bg-dark-bg"
            >
              {PAGE_SIZE_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => void runQuery(sql, { page: 0 })}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-lg bg-gov-blue-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
            Ejecutar
          </button>
        </div>
      </section>

      {writeOk && (
        <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200">
          {writeOk}
        </p>
      )}

      {error && (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-400">
          {error}
        </p>
      )}

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
        <div className="flex min-h-0 flex-1 gap-0">
          <aside className="w-[28%] min-w-[180px] max-w-[260px] overflow-y-auto border-r border-gov-gray-100 p-2 dark:border-dark-border">
            {catalogLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="animate-spin text-gov-gray-400" size={24} />
              </div>
            ) : Object.keys(schemas).length === 0 ? (
              <p className="px-2 py-4 text-xs text-gov-gray-500">Sin tablas visibles.</p>
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
                      className="flex w-full items-center gap-1 rounded-lg px-2 py-1.5 text-left text-xs font-semibold text-gov-gray-700 hover:bg-gov-gray-50 dark:text-dark-muted dark:hover:bg-dark-bg"
                    >
                      {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      <Database size={14} className="text-gov-blue-600 dark:text-dark-cyan" />
                      {schema}
                    </button>
                    {open &&
                      tables.map((tbl) => (
                        <button
                          key={`${schema}.${tbl}`}
                          type="button"
                          onClick={() => onTableClick(schema, tbl)}
                          className="flex w-full items-center gap-1 rounded-lg py-1 pl-7 pr-2 text-left font-mono text-[11px] text-gov-gray-600 hover:bg-gov-gray-50 hover:text-gov-gray-900 dark:text-dark-muted dark:hover:bg-dark-bg dark:hover:text-dark-text"
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

          <div className="min-w-0 flex-1 overflow-auto">
            {loading && rows.length === 0 ? (
              <div className="flex h-full min-h-[240px] items-center justify-center">
                <Loader2 className="animate-spin text-gov-gray-400" size={32} />
              </div>
            ) : visibleRows.length === 0 && !writeOk ? (
              <p className="p-6 text-sm text-gov-gray-500 dark:text-dark-muted">
                Selecciona una tabla o ejecuta SQL.
              </p>
            ) : (
              <table className="w-full border-collapse text-xs">
                <thead className="sticky top-0 z-10 bg-gov-gray-50 dark:bg-dark-bg">
                  {table.getHeaderGroups().map((hg) => (
                    <tr key={hg.id}>
                      {hg.headers.map((h) => (
                        <th
                          key={h.id}
                          className="whitespace-nowrap border-b border-gov-gray-200 px-3 py-2 text-left font-semibold text-gov-gray-700 dark:border-dark-border dark:text-dark-muted"
                        >
                          {flexRender(h.column.columnDef.header, h.getContext())}
                        </th>
                      ))}
                    </tr>
                  ))}
                </thead>
                <tbody>
                  {table.getRowModel().rows.map((row) => (
                    <tr key={row.id} className="hover:bg-gov-gray-50 dark:hover:bg-dark-bg/80">
                      {row.getVisibleCells().map((cell) => (
                        <td
                          key={cell.id}
                          className="max-w-[320px] truncate whitespace-nowrap border-b border-gov-gray-100 px-3 py-1.5 font-mono text-gov-gray-800 dark:border-dark-border dark:text-dark-text"
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

        {columns.length > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-gov-gray-100 px-4 py-2 dark:border-dark-border">
            <p className="text-xs text-gov-gray-500 dark:text-dark-muted">{rowRangeLabel}</p>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={exportCsv}
                disabled={visibleRows.length === 0}
                className="inline-flex items-center gap-1 rounded-lg border border-gov-gray-200 px-2.5 py-1 text-xs font-semibold dark:border-dark-border disabled:opacity-50"
              >
                <Download size={12} />
                CSV
              </button>
              <button
                type="button"
                onClick={goPrev}
                disabled={!canPrev || loading}
                className="inline-flex items-center rounded-lg border border-gov-gray-200 p-1.5 dark:border-dark-border disabled:opacity-40"
                aria-label="Página anterior"
              >
                <ChevronLeft size={14} />
              </button>
              <span className="min-w-[4rem] text-center text-xs tabular-nums text-gov-gray-600 dark:text-dark-muted">
                pág. {pageIndex + 1}
              </span>
              <button
                type="button"
                onClick={goNext}
                disabled={!canNext || loading}
                className="inline-flex items-center rounded-lg border border-gov-gray-200 p-1.5 dark:border-dark-border disabled:opacity-40"
                aria-label="Página siguiente"
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>

      {catalogMeta && (
        <div className="grid gap-2 text-xs text-gov-gray-500 dark:text-dark-muted sm:grid-cols-3">
          <MetaChip label="Actor" value={catalogMeta.actor_email || '—'} />
          <MetaChip label="Usuario vault" value={catalogMeta.vault_user_id || '—'} />
          <MetaChip label="Tenant" value={catalogMeta.tenant_id || '—'} />
        </div>
      )}
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

function MetaChip({ label, value }: { label: string; value: string }) {
  return (
    <p className="truncate">
      <span className="font-medium text-gov-gray-600 dark:text-dark-muted">{label}:</span>{' '}
      <span className="font-mono">{value}</span>
    </p>
  );
}
