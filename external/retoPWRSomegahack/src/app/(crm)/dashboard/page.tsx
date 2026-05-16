import { Metadata } from 'next';
import { TicketTable, OverdueBanner } from '@/components/dashboard';
import NuevoTicketSimulator from '@/components/dashboard/NuevoTicketSimulator';


export const metadata: Metadata = {
  title: 'Bandeja de Entrada · CRM PQRSD',
  description: 'Gestión de PQRSDs del Distrito de Medellín',
};

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      {/* Alerta Legal de Vencimiento */}
      <OverdueBanner />

      {/* Encabezado de página */}
      <div className="border-b border-gov-gray-100 dark:border-dark-border pb-2">
        <h1 className="text-2xl font-bold text-gov-gray-900 dark:text-dark-text tracking-tight">
          Bandeja de Entrada
        </h1>
        <p className="text-sm text-gov-gray-500 dark:text-dark-muted mt-1">
          Gestiona las solicitudes PQRSD asignadas a tu dependencia
        </p>
      </div>
      
      {/* Componente principal de la tabla (Client Component) */}
      <TicketTable />

      {/* Simulador de Demo (Hackathon) */}
      <div className="mt-2">
        <NuevoTicketSimulator />
      </div>
      
      {/* Aviso institucional inferior */}
      <footer className="pt-8">
        <div className="bg-gov-blue-50/50 dark:bg-dark-surface p-4 rounded-xl border border-gov-blue-100/50 dark:border-dark-border">
          <p className="text-[11px] text-gov-blue-700 dark:text-dark-cyan font-medium flex items-center gap-2">
            <span className="flex w-1.5 h-1.5 bg-gov-blue-500 rounded-full animate-pulse" />
            Sistema en cumplimiento con la Ley 1755 de 2015 sobre el Derecho de Petición.
          </p>
        </div>
      </footer>
    </div>
  );
}
