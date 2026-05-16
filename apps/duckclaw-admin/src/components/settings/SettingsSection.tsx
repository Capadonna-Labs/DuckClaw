'use client';

interface SettingsSectionProps {
  titulo: string;
  descripcion?: string;
  children: React.ReactNode;
  icono: React.ReactNode;
}

export default function SettingsSection({
  titulo,
  descripcion,
  children,
  icono
}: SettingsSectionProps) {
  return (
    <section className="bg-white dark:bg-dark-surface rounded-3xl border border-gov-gray-100 dark:border-dark-border shadow-sm overflow-hidden transition-all">
      <div className="p-6">
        <div className="flex items-start gap-4 mb-6">
          <div className="p-3 bg-gov-gray-50 dark:bg-dark-bg rounded-2xl text-gov-blue-700 dark:text-dark-cyan">
            {icono}
          </div>
          <div>
            <h2 className="text-lg font-bold text-gov-gray-900 dark:text-dark-text tracking-tight">
              {titulo}
            </h2>
            {descripcion && (
              <p className="text-sm text-gov-gray-500 dark:text-dark-muted mt-0.5">
                {descripcion}
              </p>
            )}
          </div>
        </div>
        
        <div className="border-t border-gov-gray-100 dark:border-dark-border pt-6">
          {children}
        </div>
      </div>
    </section>
  );
}
