'use client';

import { ShieldCheck } from 'lucide-react';

export function SecurityPolicyInfoPanel() {
  return (
    <section className="rounded-2xl border border-gov-gray-100 bg-gov-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
      <p className="flex items-center gap-2 text-sm font-black text-gov-gray-900 dark:text-dark-text">
        <ShieldCheck size={16} className="text-gov-blue-700 dark:text-dark-cyan" />
        Política de sandbox (automática)
      </p>
      <p className="mt-2 text-[11px] leading-relaxed text-gov-gray-600 dark:text-dark-muted">
        Este archivo controla el contenedor cuando el agente ejecuta código (
        <code className="font-mono">run_sandbox</code>): red, tiempo máximo y volúmenes.
        La plataforma crea una política <strong>zero-trust</strong> (red denegada) si no existe.
        No necesitas editarlo salvo que quieras permitir dominios concretos o más tiempo de CPU.
      </p>
      <ul className="mt-2 list-inside list-disc text-[11px] text-gov-gray-600 dark:text-dark-muted">
        <li>
          <code className="font-mono">network.default: deny</code> — sin internet en el contenedor
        </li>
        <li>
          <code className="font-mono">max_execution_time_seconds</code> — límite de ejecución
        </li>
        <li>Activa/desactiva sandbox por chat en Playground con el chip Sandbox</li>
      </ul>
    </section>
  );
}
