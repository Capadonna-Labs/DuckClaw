import { InboxIcon, SearchX, AlertTriangle, ShieldOff, RotateCcw } from 'lucide-react';
import { cn } from '@/lib/utils';

type EmptyStateVariant = 'empty' | 'filtered' | 'error' | 'unauthorized';

interface EmptyStateProps {
  variant: EmptyStateVariant;
  customMessage?: string;
  onAction?: () => void;
  actionLabel?: string;
}

const variantConfig = {
  empty: {
    icon: InboxIcon,
    iconClass: 'text-gov-gray-300',
    title: 'Bandeja vacía',
    description: 'No hay PQRSDs asignados a tu dependencia en este momento.',
  },
  filtered: {
    icon: SearchX,
    iconClass: 'text-gov-blue-300',
    title: 'Sin resultados',
    description: 'Ningún ticket coincide con los filtros aplicados.',
  },
  error: {
    icon: AlertTriangle,
    iconClass: 'text-sem-red',
    title: 'Error al cargar',
    description: 'No se pudo cargar la información. Intenta de nuevo.',
  },
  unauthorized: {
    icon: ShieldOff,
    iconClass: 'text-gov-gray-400',
    title: 'Acceso no autorizado',
    description: 'No tienes permisos para ver este recurso. Solo puedes gestionar tickets de tu dependencia asignada.',
  },
};

export default function EmptyState({ 
  variant, 
  customMessage, 
  onAction, 
  actionLabel 
}: EmptyStateProps) {
  const config = variantConfig[variant];
  const Icon = config.icon;

  return (
    <div className="flex flex-col items-center justify-center py-20 px-4 text-center">
      <div className={cn("p-4 rounded-full bg-white dark:bg-dark-surface border border-gov-gray-50 dark:border-dark-border shadow-sm mb-4", config.iconClass)}>
        <Icon size={48} strokeWidth={1.5} />
      </div>
      
      <h3 className="text-lg font-bold text-gov-gray-900 dark:text-dark-text mb-1 leading-tight">
        {config.title}
      </h3>
      
      <p className="text-sm text-gov-gray-500 dark:text-dark-muted max-w-xs leading-relaxed">
        {customMessage || config.description}
      </p>

      {onAction && (
        <button
          onClick={onAction}
          className={cn(
            "mt-6 flex items-center gap-2 px-5 py-2.5 rounded-lg font-semibold text-sm transition-all",
            variant === 'error' || variant === 'unauthorized'
              ? "bg-gov-blue-700 text-white hover:bg-gov-blue-900 shadow-lg shadow-gov-blue-900/20"
              : "text-gov-blue-700 hover:bg-gov-blue-50 border border-gov-blue-200"
          )}
        >
          {variant === 'error' && <RotateCcw size={16} />}
          {actionLabel || (variant === 'filtered' ? 'Limpiar filtros' : variant === 'error' ? 'Reintentar' : 'Volver al inicio')}
        </button>
      )}
    </div>
  );
}
