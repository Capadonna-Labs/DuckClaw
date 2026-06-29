import Link from 'next/link';
import { PageShell } from '@/components/admin/PageShell';
import { Cable, Circle, Database, Link2, Package, Terminal } from 'lucide-react';

const MCP_ROUTES = [
  {
    href: "/mcp/connectors",
    title: 'Conectores MCP',
    description: 'Registry DB-first, Higgsfield, grants por worker.',
    icon: Link2,
  },
  {
    href: "/mcp/runtime",
    title: 'Estado runtime MCP',
    description: 'Proceso HTTP, PM2 y comprobación.',
    icon: Circle,
  },
  {
    href: "/mcp/config",
    title: 'Configuración MCP',
    description: 'Puerto DB-first y fuente efectiva.',
    icon: Database,
  },
  {
    href: "/mcp/server",
    title: 'Servidor DuckClaw MCP',
    description: 'Comando local y endpoint HTTP.',
    icon: Terminal,
  },
  {
    href: "/mcp/tools",
    title: 'Herramientas MCP',
    description: 'Tools expuestas por DuckClaw MCP.',
    icon: Cable,
  },
  {
    href: "/mcp/catalog",
    title: 'Catálogo MCP',
    description: 'Referencia oficial y stdio solo lectura.',
    icon: Package,
  },
] as const;

export default function McpPage() {
  return (
    <PageShell>
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">MCP</h1>
        <p className="mt-1 max-w-2xl text-sm text-gov-gray-500 dark:text-dark-muted">
          Cada responsabilidad MCP vive en una vista dedicada.
        </p>
      </header>

      <section className="grid gap-4 md:grid-cols-2">
        {MCP_ROUTES.map((route) => (
          <McpRouteCard key={route.href} {...route} />
        ))}
      </section>
    </PageShell>
  );
}

function McpRouteCard({
  href,
  title,
  description,
  icon: Icon,
}: {
  href: string;
  title: string;
  description: string;
  icon: typeof Circle;
}) {
  return (
    <Link
      href={href}
      className="group rounded-3xl border border-gov-gray-100 bg-white p-5 shadow-sm transition-all hover:-translate-y-0.5 hover:border-gov-blue-300 hover:shadow-md dark:border-dark-border dark:bg-dark-surface"
    >
      <div className="flex items-start gap-3">
        <span className="rounded-2xl bg-gov-blue-50 p-3 text-gov-blue-700 dark:bg-dark-bg dark:text-dark-cyan">
          <Icon size={22} />
        </span>
        <div>
          <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">{title}</h2>
          <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">{description}</p>
        </div>
      </div>
    </Link>
  );
}
