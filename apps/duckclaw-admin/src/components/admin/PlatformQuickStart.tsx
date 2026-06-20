'use client';

import Link from 'next/link';
import { Bot, Database, MessageCircle } from 'lucide-react';

export function PlatformQuickStart() {
  return (
    <section className="rounded-3xl border border-gov-blue-100 bg-gradient-to-br from-gov-blue-50 to-white p-5 dark:border-dark-border dark:from-dark-bg dark:to-dark-surface">
      <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">Empezar en 3 pasos</h2>
      <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
        La plataforma incluye herramientas base; tú solo creas el agente, conectas conocimiento y conversas.
      </p>
      <ol className="mt-4 grid gap-3 md:grid-cols-3">
        <Step
          n={1}
          href="/templates"
          icon={Bot}
          title="Crear agente"
          body="Nombre + instrucciones. SQL, RAG y sandbox vienen incluidos."
        />
        <Step
          n={2}
          href="/knowledge"
          icon={Database}
          title="Conectar RAG"
          body="Importa tu vault o carpeta. El agente listará y leerá documentos."
        />
        <Step
          n={3}
          href="/playground"
          icon={MessageCircle}
          title="Conversar"
          body="Elige proyecto y agente. Activa sandbox si necesitas ejecutar código."
        />
      </ol>
    </section>
  );
}

function Step({
  n,
  href,
  icon: Icon,
  title,
  body,
}: {
  n: number;
  href: string;
  icon: React.ElementType;
  title: string;
  body: string;
}) {
  return (
    <li>
      <Link
        href={href}
        className="flex h-full flex-col rounded-2xl border border-white/80 bg-white/90 p-4 shadow-sm transition hover:border-gov-blue-200 dark:border-dark-border dark:bg-dark-surface dark:hover:border-gov-blue-700"
      >
        <span className="text-[10px] font-black uppercase text-gov-blue-700 dark:text-dark-cyan">Paso {n}</span>
        <Icon size={20} className="mt-2 text-gov-blue-700 dark:text-dark-cyan" />
        <p className="mt-2 font-black text-gov-gray-900 dark:text-dark-text">{title}</p>
        <p className="mt-1 text-xs text-gov-gray-500 dark:text-dark-muted">{body}</p>
      </Link>
    </li>
  );
}
