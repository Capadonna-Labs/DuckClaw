import { NivelUrgencia } from '@/types';
import { getUrgencyConfig } from '@/lib/urgency';
import { cn } from '@/lib/utils';

interface UrgencyBadgeProps {
  nivelUrgencia: NivelUrgencia;
  diasRestantes: number;
  /** Si true, muestra solo el círculo de color sin texto */
  compact?: boolean;
}

export default function UrgencyBadge({ 
  nivelUrgencia, 
  diasRestantes, 
  compact = false 
}: UrgencyBadgeProps) {
  const config = getUrgencyConfig(nivelUrgencia);
  
  const isVencido = diasRestantes < 0;
  const labelText = isVencido ? 'VENCIDO' : config.label;
  const daysText = `${Math.abs(diasRestantes)}d`;

  const ariaLabel = `Urgencia: ${labelText}. ${diasRestantes} días restantes`;

  if (compact) {
    return (
      <div 
        role="status"
        aria-label={ariaLabel}
        title={`${labelText} - ${diasRestantes} días`}
        className={cn(
          "w-2.5 h-2.5 rounded-full flex-shrink-0",
          config.textColor.replace('text-', 'bg-') // Usa el color sólido para el círculo
        )}
      />
    );
  }

  return (
    <div 
      role="status"
      aria-label={ariaLabel}
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] tracking-wide font-bold border whitespace-nowrap",
        config.bgColor,
        config.textColor,
        config.borderColor.replace('border-', 'border-opacity-30 border-')
      )}
    >
      <span className="text-[8px] opacity-70">●</span>
      <span>
        {labelText} · {daysText}
      </span>
    </div>
  );
}
