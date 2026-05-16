import { Clock, Eye, CheckCircle2 } from 'lucide-react';
import { TicketEstado } from '@/types';
import { cn } from '@/lib/utils';

interface StatusBadgeProps {
  estado: TicketEstado;
}

const statusConfig = {
  Pendiente: {
    label: 'Pendiente',
    icon: Clock,
    className: 'bg-gov-blue-100 text-gov-blue-700 dark:bg-dark-accent/20 dark:text-dark-cyan',
  },
  En_Revision: {
    label: 'En Revisión',
    icon: Eye,
    className: 'bg-gov-gold-100 text-gov-gold-500 dark:bg-gov-gold-500/10 dark:text-gov-gold-500',
  },
  Resuelto: {
    label: 'Resuelto',
    icon: CheckCircle2,
    className: 'bg-sem-green-bg text-sem-green dark:bg-sem-green/10 dark:text-sem-green',
  },
};

export default function StatusBadge({ estado }: StatusBadgeProps) {
  const config = statusConfig[estado];
  const Icon = config.icon;

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold whitespace-nowrap",
        config.className
      )}
    >
      <Icon size={14} strokeWidth={2.5} />
      <span>{config.label}</span>
    </div>
  );
}
