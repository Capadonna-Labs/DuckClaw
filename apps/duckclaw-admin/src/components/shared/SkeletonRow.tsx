import { cn } from '@/lib/utils';

/**
 * COMPONENTE 1: SkeletonRow
 * Imitación exacta de la estructura de TicketRow para el Dashboard.
 */
export default function SkeletonRow() {
  const skeletonBase = "animate-pulse bg-gov-gray-100 dark:bg-dark-border rounded";

  return (
    <tr className="border-b border-gov-gray-100 dark:border-dark-border">
      {/* 1. Urgency Circle */}
      <td className="py-4 pl-4 w-12 text-center">
        <div className="inline-block w-3 h-3 rounded-full bg-gov-gray-200 dark:bg-dark-border animate-pulse" />
      </td>

      {/* 2. ID / Canal */}
      <td className="py-4 px-3 w-40">
        <div className="flex flex-col gap-2">
          <div className={cn(skeletonBase, "w-20 h-3")} />
          <div className={cn(skeletonBase, "w-16 h-2")} />
        </div>
      </td>

      {/* 3. Ciudadano / Tipo */}
      <td className="py-4 px-3 flex-1">
        <div className="flex flex-col gap-2">
          <div className={cn(skeletonBase, "w-48 h-4")} />
          <div className={cn(skeletonBase, "w-32 h-2")} />
        </div>
      </td>

      {/* 4. Estado */}
      <td className="py-4 px-3">
        <div className={cn(skeletonBase, "w-20 h-6 rounded-full")} />
      </td>

      {/* 5. Urgencia */}
      <td className="py-4 px-3 w-36">
        <div className={cn(skeletonBase, "w-24 h-6 rounded-full")} />
      </td>

      {/* 6. Fecha */}
      <td className="py-4 px-3 w-32">
        <div className={cn(skeletonBase, "w-20 h-3")} />
      </td>

      {/* 7. Chevron */}
      <td className="py-4 pr-4 w-8 text-right">
        <div className={cn(skeletonBase, "w-4 h-4 rounded-full float-right")} />
      </td>
    </tr>
  );
}

/**
 * COMPONENTE 2: SkeletonDetailPage
 * Estructura de carga para la vista de detalle del ticket.
 */
export function SkeletonDetailPage() {
  const skeletonBase = "animate-pulse bg-gov-gray-100 dark:bg-dark-border rounded";

  return (
    <div className="space-y-6">
      {/* Botón Volver Placeholder */}
      <div className={cn(skeletonBase, "w-40 h-4 mb-6")} />

      <div className="grid grid-cols-1 lg:grid-cols-[55fr_45fr] gap-8">
        {/* Columna Izquierda: Información */}
        <div className="bg-white dark:bg-dark-surface rounded-2xl border border-gov-gray-100 dark:border-dark-border p-8 space-y-8">
          {/* Cabecera */}
          <div className="space-y-4">
            <div className="flex gap-2">
              <div className={cn(skeletonBase, "w-16 h-5")} />
              <div className={cn(skeletonBase, "w-20 h-5")} />
              <div className={cn(skeletonBase, "w-24 h-5")} />
            </div>
            <div className={cn(skeletonBase, "w-3/4 h-8 mt-2")} />
            <div className={cn(skeletonBase, "w-1/2 h-4")} />
          </div>

          {/* Metadatos Grid */}
          <div className="grid grid-cols-2 gap-4">
             {Array.from({ length: 4 }).map((_, i) => (
               <div key={i} className={cn(skeletonBase, "h-20 w-full rounded-xl")} />
             ))}
          </div>

          {/* Bloque Texto Largo */}
          <div className="space-y-4">
            <div className={cn(skeletonBase, "w-1/3 h-5 mb-4")} />
            <div className="space-y-2">
              <div className={cn(skeletonBase, "w-full h-4")} />
              <div className={cn(skeletonBase, "w-full h-4")} />
              <div className={cn(skeletonBase, "w-full h-4")} />
              <div className={cn(skeletonBase, "w-2/3 h-4")} />
            </div>
          </div>
        </div>

        {/* Columna Derecha: Editor */}
        <div className="space-y-6">
          <div className="bg-white dark:bg-dark-surface border border-gov-gray-100 dark:border-dark-border rounded-2xl p-6 space-y-6">
            <div className={cn(skeletonBase, "w-1/2 h-6")} />
            <div className={cn(skeletonBase, "w-full h-64 rounded-xl")} />
            <div className={cn(skeletonBase, "w-full h-12 rounded-lg")} />
            
            <div className="flex justify-between items-center pt-4 border-t border-gov-gray-100">
               <div className={cn(skeletonBase, "w-32 h-10")} />
               <div className={cn(skeletonBase, "w-40 h-12 rounded-xl")} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
