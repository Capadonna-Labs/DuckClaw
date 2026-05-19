'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { adminService } from '@/services/adminService';
import { useAuthStore } from '@/store/authStore';
import EmptyState from '@/components/shared/EmptyState';
import ConfirmDangerModal from '@/components/admin/ConfirmDangerModal';
import { FolderKanban, Plus, Users } from 'lucide-react';

type ForgeProject = Awaited<ReturnType<typeof adminService.listForgeProjects>>[number];

export default function ProjectsPage() {
  const { usuario } = useAuthStore();
  const canWrite = usuario?.rol === 'admin';
  const [items, setItems] = useState<ForgeProject[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<ForgeProject | null>(null);
  const [applying, setApplying] = useState<string | null>(null);

  const reload = useCallback(() => {
    adminService
      .listForgeProjects()
      .then(setItems)
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const applyTeam = async (slug: string) => {
    setApplying(slug);
    setError(null);
    try {
      await adminService.applyForgeProjectTeam(slug);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo aplicar equipo');
    } finally {
      setApplying(null);
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete || !canWrite) return;
    try {
      await adminService.deleteForgeProject(pendingDelete.slug);
      setPendingDelete(null);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo eliminar');
    }
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black text-gov-gray-900 dark:text-dark-text flex items-center gap-2">
            <FolderKanban size={28} /> Proyectos
          </h1>
          <p className="text-sm text-gov-gray-500 dark:text-dark-muted mt-1">
            Agrupaciones lógicas en <code className="text-xs">forge/projects/</code> (no mueven carpetas de
            templates)
          </p>
        </div>
        {canWrite && (
          <Link
            href="/projects/new"
            className="inline-flex items-center gap-2 px-4 py-2 bg-gov-blue-700 text-white text-sm font-bold rounded-xl"
          >
            <Plus size={16} /> Nuevo proyecto o agente
          </Link>
        )}
      </header>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      {items.length === 0 ? (
        <EmptyState
          variant="empty"
          customMessage="Sin proyectos. Crea uno en disco o define presets en .env (ver forge/projects/README.md)."
          actionLabel="Crear proyecto"
          onAction={() => {
            window.location.href = '/projects/new';
          }}
        />
      ) : (
        <div className="grid gap-4">
          {items.map((p) => (
            <article
              key={p.slug}
              className="bg-white dark:bg-dark-surface rounded-2xl border dark:border-dark-border p-5"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-bold">{p.display_name}</h2>
                  <p className="text-xs text-gov-gray-500 font-mono mt-0.5">{p.path}</p>
                  {p.coordinator && (
                    <p className="text-xs mt-2">
                      Coordinador: <strong>{p.coordinator}</strong>
                    </p>
                  )}
                  {p.source === 'env' && (
                    <span className="inline-block mt-2 text-[10px] px-2 py-0.5 rounded-full bg-gov-cyan-100 text-gov-blue-800">
                      .env
                    </span>
                  )}
                </div>
                {canWrite && (
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={applying === p.slug}
                      onClick={() => void applyTeam(p.slug)}
                      className="inline-flex items-center gap-1 px-3 py-2 text-xs font-bold rounded-xl border dark:border-dark-border hover:border-gov-blue-500 disabled:opacity-50"
                    >
                      <Users size={14} />
                      {applying === p.slug ? 'Aplicando…' : 'Aplicar equipo al tenant'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setPendingDelete(p)}
                      className="px-3 py-2 text-xs font-bold rounded-xl text-red-700 border border-red-200"
                    >
                      Eliminar
                    </button>
                  </div>
                )}
              </div>
              <ul className="mt-3 flex flex-wrap gap-2">
                {(p.members ?? []).map((m) => (
                  <li key={m}>
                    <Link
                      href={`/templates/${m}`}
                      className="text-xs px-2 py-1 rounded-lg bg-gov-gray-100 dark:bg-dark-bg font-mono hover:text-gov-blue-700"
                    >
                      {m}
                    </Link>
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      )}

      <ConfirmDangerModal
        isOpen={Boolean(pendingDelete)}
        title="Eliminar proyecto"
        description={`Se borrará forge/projects/${pendingDelete?.slug}/. Los templates en disco no se eliminan.`}
        confirmLabel="Eliminar"
        details={
          pendingDelete
            ? [
                { label: 'Slug', value: pendingDelete.slug },
                { label: 'Miembros', value: (pendingDelete.members ?? []).join(', ') || '—' },
              ]
            : []
        }
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}
