import Link from 'next/link';
import { ProjectManagedWorkspaceDraftWizard } from '@/components/projects/ProjectManagedWorkspaceDraftWizard';

export default function ProjectManagedWorkspaceDraftPage() {
  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-2">
        <Link href="/projects" className="text-sm font-bold text-gov-blue-700 dark:text-dark-cyan">
          Volver al catalogo
        </Link>
        <h1 className="text-3xl font-black text-gov-gray-900 dark:text-dark-text">
          Nuevo proyecto con borrador administrado
        </h1>
        <p className="text-sm text-gov-gray-500 dark:text-dark-muted">
          El flujo administrado prepara un borrador DB-first y nada se guarda hasta confirmar.
        </p>
      </header>

      <ProjectManagedWorkspaceDraftWizard />
    </div>
  );
}
