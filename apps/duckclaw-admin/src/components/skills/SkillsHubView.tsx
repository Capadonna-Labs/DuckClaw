import Link from 'next/link';
import { BarChart3, Blocks, Plus } from 'lucide-react';
import { ViewChrome, type EmbeddedViewProps } from '@/components/admin/embeddedView';

export default function SkillsHubView({ embedded = false }: EmbeddedViewProps) {
  return (
    <ViewChrome embedded={embedded}>
      {!embedded && (
        <header>
          <h1 className="text-3xl font-black dark:text-dark-text">Skills</h1>
          <p className="mt-1 max-w-2xl text-sm text-gov-gray-500 dark:text-dark-muted">
            Administra cada responsabilidad en una vista separada.
          </p>
        </header>
      )}

      <section className="grid gap-4 md:grid-cols-2">
        <SkillRouteCard
          href="/skills/summary"
          title="Resumen"
          description="Conteo global/local y estado del inventario."
          icon={<BarChart3 size={22} />}
        />
        <SkillRouteCard
          href="/skills/new"
          title="Nueva skill"
          description="Crear metadata DB-first privada."
          icon={<Plus size={22} />}
        />
        <SkillRouteCard
          href="/skills/global"
          title="Skills globales"
          description="Capacidades reutilizables entre agentes."
          icon={<Blocks size={22} />}
        />
        <SkillRouteCard
          href="/skills/local"
          title="Skills locales"
          description="Capacidades específicas de workers."
          icon={<Blocks size={22} />}
        />
      </section>
    </ViewChrome>
  );
}

function SkillRouteCard({
  href,
  title,
  description,
  icon,
}: {
  href: string;
  title: string;
  description: string;
  icon: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="group rounded-3xl border border-gov-gray-100 bg-white p-5 shadow-sm transition-all hover:-translate-y-0.5 hover:border-gov-blue-300 hover:shadow-md dark:border-dark-border dark:bg-dark-surface"
    >
      <div className="flex items-start gap-3">
        <span className="rounded-2xl bg-gov-blue-50 p-3 text-gov-blue-700 dark:bg-dark-bg dark:text-dark-cyan">
          {icon}
        </span>
        <div>
          <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">{title}</h2>
          <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">{description}</p>
        </div>
      </div>
    </Link>
  );
}
