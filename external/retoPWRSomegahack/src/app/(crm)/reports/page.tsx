'use client';

import { useAnalytics } from '@/hooks/useAnalytics';
import { useAuthStore } from '@/store/authStore';
import { MetricCard, GraficaBarras, GraficaDonut, GraficaCanales, GraficaTendenciaArea } from '@/components/reports';
import { 
  BarChart3, 
  Clock, 
  AlertTriangle, 
  Percent, 
  Users,
  Calendar,
  Download
} from 'lucide-react';

export default function ReportsPage() {
  const { 
    metricas, 
    distribucionPorTipo, 
    distribucionPorCanal, 
    tendenciaSemanal,
    tendenciaDiaria,
    isLoading 
  } = useAnalytics();
  
  const { usuario } = useAuthStore();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gov-blue-700" />
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-in fade-in duration-700">
      {/* 1. CABECERA DE REPORTES */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gov-gray-900 dark:text-dark-text tracking-tight flex items-center gap-2">
            <BarChart3 className="text-gov-blue-700 dark:text-dark-cyan" size={24} />
            Reportes y Analytics
          </h1>
          <p className="text-sm text-gov-gray-500 dark:text-dark-muted mt-1">
            Métricas de gestión de PQRSDs · <span className="font-bold text-gov-blue-700 dark:text-dark-cyan">{usuario?.secretariaNombre}</span>
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button className="flex items-center gap-2 px-4 py-2 bg-white dark:bg-dark-surface border border-gov-gray-200 dark:border-dark-border rounded-xl text-xs font-bold text-gov-gray-600 dark:text-dark-text hover:bg-gov-gray-50 dark:hover:bg-dark-border transition-colors shadow-sm">
            <Calendar size={14} />
            Últimos 30 días
          </button>
          <button className="flex items-center gap-2 px-4 py-2 bg-gov-blue-700 text-white rounded-xl text-xs font-bold hover:bg-gov-blue-900 transition-colors shadow-lg shadow-gov-blue-900/20">
            <Download size={14} />
            Exportar PDF
          </button>
        </div>
      </div>

      {/* ESTADO DE CONEXIÓN */}
      <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-sem-green bg-sem-green-bg dark:bg-sem-green/10 px-4 py-2 rounded-full border border-sem-green/20 w-fit">
        <span className="w-2 h-2 bg-sem-green rounded-full animate-pulse" />
        Datos en tiempo real · Medellín GovTech Monitoring
      </div>

      {/* 2. GRID DE MÉTRICAS MOCK/REALES */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <MetricCard 
          titulo="Total Tickets" 
          valor={metricas.totalTickets} 
          subtitulo="PQRSDs recibidos"
          icono={<Users size={20} />} 
          bgIcono="bg-gov-blue-100" 
          colorIcono="text-gov-blue-700" 
        />
        <MetricCard 
          titulo="Tasa de Cumplimiento" 
          valor={`${metricas.tasaCumplimiento}%`}
          subtitulo="dentro del plazo legal"
          icono={<Percent size={20} />} 
          bgIcono="bg-sem-green-bg" 
          colorIcono="text-sem-green"
          tendencia={{ valor: 4.2, positivo: true }} 
        />
        <MetricCard 
          titulo="Tickets Críticos" 
          valor={metricas.ticketsCriticos}
          subtitulo="requieren atención"
          icono={<AlertTriangle size={20} />} 
          bgIcono="bg-sem-red-bg" 
          colorIcono="text-sem-red"
        />
        <MetricCard 
          titulo="Promedio Respuesta" 
          valor={`${metricas.promedioRespuestaDias}d`}
          subtitulo="días hábiles promedio"
          icono={<Clock size={20} />} 
          bgIcono="bg-gov-gold-100" 
          colorIcono="text-gov-gold-500" 
        />
      </div>

      {/* 3. GRÁFICAS PRINCIPALES */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Tendencia semanal — ocupa 2/3 */}
        <div className="lg:col-span-2 bg-white dark:bg-dark-surface rounded-3xl border border-gov-gray-100 dark:border-dark-border p-6 shadow-sm">
          <div className="flex items-center justify-between mb-8">
            <h2 className="text-sm font-black text-gov-gray-800 dark:text-dark-text uppercase tracking-widest">
              Tendencia de Gestión (Semanas)
            </h2>
            <div className="flex gap-4">
               <div className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-gov-blue-700" />
                  <span className="text-[10px] font-bold text-gov-gray-500 uppercase">Ingresos</span>
               </div>
               <div className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-sem-green" />
                  <span className="text-[10px] font-bold text-gov-gray-500 uppercase">Resueltos</span>
               </div>
            </div>
          </div>
          <GraficaBarras data={tendenciaSemanal} />
        </div>

        {/* Distribución por tipo — ocupa 1/3 */}
        <div className="bg-white dark:bg-dark-surface rounded-3xl border border-gov-gray-100 dark:border-dark-border p-6 shadow-sm overflow-hidden flex flex-col">
          <h2 className="text-sm font-black text-gov-gray-800 dark:text-dark-text uppercase tracking-widest mb-4">
            Distribución por Tipo
          </h2>
          <div className="flex-1">
            <GraficaDonut data={distribucionPorTipo} />
          </div>
          <div className="space-y-2 mt-4 pt-4 border-t border-gov-gray-50">
            {distribucionPorTipo.map(d => (
              <div key={d.tipo} className="flex justify-between items-center text-[10px] font-bold">
                <span className="flex items-center gap-2 text-gov-gray-600 dark:text-dark-muted">
                  <span style={{ backgroundColor: d.color }} className="w-2 h-2 rounded-full shadow-sm" />
                  {d.tipo}
                </span>
                <span className="text-gov-gray-900 dark:text-dark-text">{d.cantidad} <span className="text-gov-gray-400 dark:text-dark-muted/50 font-medium ml-1">({d.porcentaje}%)</span></span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 4. EVOLUCIÓN DIARIA Y CANALES */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="bg-white dark:bg-dark-surface rounded-3xl border border-gov-gray-100 dark:border-dark-border p-6 shadow-sm">
          <div className="flex items-center justify-between mb-8">
            <h2 className="text-sm font-black text-gov-gray-800 dark:text-dark-text uppercase tracking-widest">
              Actividad Diaria (Tickets)
            </h2>
            <div className="px-3 py-1 bg-gov-cyan-50 dark:bg-dark-accent/10 rounded-full text-[9px] font-black text-gov-cyan-600 dark:text-dark-cyan uppercase">
              Última semana
            </div>
          </div>
          <GraficaTendenciaArea data={tendenciaDiaria} />
        </div>

        <div className="bg-white dark:bg-dark-surface rounded-3xl border border-gov-gray-100 dark:border-dark-border p-6 shadow-sm">
          <h2 className="text-sm font-black text-gov-gray-800 dark:text-dark-text uppercase tracking-widest mb-8">
            Volumen por Canal de Origen
          </h2>
          <GraficaCanales data={distribucionPorCanal} />
        </div>
      </div>
    </div>
  );
}
