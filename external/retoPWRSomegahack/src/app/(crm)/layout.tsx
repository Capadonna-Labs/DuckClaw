'use client';

import React, { useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore } from '@/store/authStore';
import { Sidebar, Topbar } from '@/components/layout';
import { Loader2 } from 'lucide-react';

/**
 * CRM Layout Master
 * Envuelve todas las páginas privilegiadas del sistema.
 * Implementa protección de rutas y navegación dinámica.
 */
export default function CRMLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isAuthenticated, isLoading } = useAuthStore();
  const router = useRouter();
  const pathname = usePathname();
  const [isSidebarOpen, setIsSidebarOpen] = React.useState(false);

  // 1. Protección de Rutas (Frontend Guard)
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/login');
    }
    // Cerrar sidebar al cambiar de ruta en móvil
    setIsSidebarOpen(false);
  }, [isAuthenticated, isLoading, router, pathname]);

  // 2. Determinación dinámica del título
  const getHeaderTitle = () => {
    if (pathname.startsWith('/dashboard')) return 'Bandeja de Entrada';
    if (pathname.startsWith('/ticket')) return 'Detalle de Solicitud';
    if (pathname.startsWith('/reports')) return 'Analítica y Reportes';
    if (pathname.startsWith('/settings')) return 'Configuración';
    return 'Panel de Gestión';
  };

  // 3. Estado de Carga / Validación de Sesión
  if (isLoading || !isAuthenticated) {
    return (
      <div className="min-h-screen bg-gov-gray-50 flex flex-col items-center justify-center space-y-4 dark:bg-dark-bg">
        <Loader2 size={32} className="animate-spin text-gov-blue-700 dark:text-dark-cyan" />
        <p className="text-xs font-bold text-gov-gray-400 uppercase tracking-widest dark:text-dark-muted">
          Verificando Credenciales...
        </p>
      </div>
    );
  }

  // 4. Renderizado Master Layout
  return (
    <div className="flex h-screen overflow-hidden bg-gov-gray-50 dark:bg-dark-bg">
      {/* Sidebar - Desktop */}
      <div className="hidden lg:flex lg:shrink-0">
        <Sidebar />
      </div>

      {/* Sidebar - Mobile (Drawer) */}
      {isSidebarOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          {/* Overlay */}
          <div 
            className="fixed inset-0 bg-gov-blue-900/60 backdrop-blur-sm" 
            onClick={() => setIsSidebarOpen(false)}
          />
          
          {/* Drawer Content */}
          <div className="relative flex w-64 flex-col animate-in slide-in-from-left duration-300">
            <Sidebar />
          </div>
        </div>
      )}

      {/* Área de Trabajo Principal */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden relative">
        {/* Barra Superior Informativa */}
        <Topbar 
          title={getHeaderTitle()} 
          onMenuClick={() => setIsSidebarOpen(true)} 
        />

        {/* Zona de contenido dinámico con Scroll Independiente */}
        <main className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-10 transition-all duration-300">
          <div className="max-w-[1600px] mx-auto">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
