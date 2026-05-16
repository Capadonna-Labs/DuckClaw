'use client';

import { useState } from 'react';
import { useAuthStore } from '@/store/authStore';
import { useRouter } from 'next/navigation';
import ThemeToggle from '@/components/settings/ThemeToggle';
import SettingsSection from '@/components/settings/SettingsSection';
import { 
  User, 
  Palette, 
  Bell, 
  Shield, 
  LogOut,
  Hash,
  Info,
  Check,
  AlertTriangle,
  Trash2
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { obtenerIniciales } from '@/lib/utils';

export default function SettingsPage() {
  const { usuario, logout } = useAuthStore();
  const router = useRouter();

  // Estado para las notificaciones
  const [notifConfig, setNotifConfig] = useState({
    criticos: true,
    vencimiento: true,
    sonido: false
  });

  const handleLogout = () => {
    logout();
    router.push('/login');
  };

  // Estado para el reset de DB
  const [isResetting, setIsResetting] = useState(false);
  const [showConfirmReset, setShowConfirmReset] = useState(false);

  const handleResetDB = async () => {
    setIsResetting(true);
    try {
      const res = await fetch('/api/admin/reset-db', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        alert('Base de datos limpiada con éxito. La página se recargará.');
        window.location.reload();
      } else {
        throw new Error(data.error);
      }
    } catch (e) {
      alert('Error: ' + (e instanceof Error ? e.message : 'Fallo el reset'));
    } finally {
      setIsResetting(false);
      setShowConfirmReset(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8 pb-12 animate-in fade-in slide-in-from-bottom-4 duration-700">
      {/* 1. CABECERA */}
      <div className="flex flex-col gap-1">
        <h1 className="text-3xl font-black text-gov-gray-900 dark:text-dark-text tracking-tighter">
          Configuración del Sistema
        </h1>
        <p className="text-sm text-gov-gray-500 dark:text-dark-muted">
          Personaliza tu entorno de gestión de PQRSDs · Medellín GovTech
        </p>
      </div>

      {/* 2. SECCIÓN: PERFIL */}
      <SettingsSection 
        titulo="Perfil del Funcionario" 
        descripcion="Datos de identificación y secretaría asignada"
        icono={<User size={22} />}
      >
        <div className="flex flex-col md:flex-row items-center gap-8 mb-8 pb-8 border-b border-gov-gray-50 dark:border-dark-border">
          <div className="relative group">
            <div className="w-24 h-24 bg-gov-blue-700 dark:bg-dark-accent rounded-3xl flex items-center justify-center text-4xl font-black text-white shadow-xl shadow-gov-blue-900/20 transition-transform group-hover:rotate-3 duration-500">
              {obtenerIniciales(usuario?.nombreCompleto || '')}
            </div>
            <div className="absolute -bottom-2 -right-2 bg-sem-green text-white p-2 rounded-xl border-4 border-white dark:border-dark-surface">
               <Check size={16} strokeWidth={3} />
            </div>
          </div>
          
          <div className="text-center md:text-left space-y-1">
            <h3 className="text-xl font-black text-gov-gray-900 dark:text-dark-text tracking-tight">
              {usuario?.nombreCompleto}
            </h3>
            <p className="text-sm font-bold text-gov-blue-700 dark:text-dark-cyan uppercase tracking-widest">
              {usuario?.rol === 'admin' ? 'Administrador de Sede' : 'Funcionario Operativo'}
            </p>
            <div className="flex items-center gap-2 justify-center md:justify-start text-xs text-gov-gray-500 dark:text-dark-muted mt-2">
               <span className="w-2 h-2 rounded-full bg-sem-green" />
               Cuenta de funcionario activa
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <ReadOnlyField label="Cargo" value={usuario?.cargo || "Gestor de Trámites"} />
          <ReadOnlyField 
            label="ID de Usuario" 
            value={usuario?.idUsuario || 'USR-0982-MED'} 
            icon={<Hash size={12} />} 
          />
          <ReadOnlyField 
            label="Correo Institucional" 
            value={usuario?.idUsuario === 'admin-001' ? 'rraliadosteam@gmail.com' : 'funcionario@medellin.gov.co'} 
          />
        </div>

        {/* --- SIMULADOR DE ROLES (NUEVO) --- */}
        <div className="mt-8 pt-8 border-t border-gov-gray-50 dark:border-dark-border">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-gov-blue-100 dark:bg-dark-sidebar rounded-lg text-gov-blue-700 dark:text-dark-cyan">
              <Shield size={18} />
            </div>
            <div>
              <p className="text-sm font-black text-gov-gray-900 dark:text-dark-text uppercase tracking-tight">Simulador de Roles y Dependencias</p>
              <p className="text-[10px] text-gov-gray-500 dark:text-dark-muted">Cambia tu adscripción para la demo</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
             <div className="space-y-2">
                <label className="text-[10px] font-black text-gov-gray-400 uppercase tracking-widest">Secretaría Activa</label>
                <select 
                  value={usuario?.idSecretaria}
                  onChange={(e) => {
                    if (!usuario) return;
                    const id = e.target.value;
                    let nombreSec = 'Secretaría de Salud';
                    if (id === 'sec-educacion') nombreSec = 'Secretaría de Educación';
                    if (id === 'sec-movilidad') nombreSec = 'Secretaría de Movilidad';
                    if (id === 'sec-cultura') nombreSec = 'Secretaría de Cultura';
                    if (id === 'sec-desarrollo') nombreSec = 'Secretaría de Desarrollo';
                    if (id === 'all') nombreSec = 'Distrito de Medellín (Global)';

                    useAuthStore.getState().setUsuario({
                      ...usuario,
                      idSecretaria: id,
                      secretariaNombre: nombreSec,
                      rol: id === 'all' ? 'alcalde' : 'admin'
                    });
                  }}
                  className="w-full px-4 py-3 bg-white dark:bg-dark-bg border border-gov-gray-200 dark:border-dark-border rounded-xl text-sm font-bold text-gov-gray-700 dark:text-dark-text focus:ring-2 focus:ring-gov-blue-500 outline-none transition-all"
                >
                  <option value="sec-salud">Secretaría de Salud</option>
                  <option value="sec-educacion">Secretaría de Educación</option>
                  <option value="sec-movilidad">Secretaría de Movilidad</option>
                  <option value="sec-cultura">Secretaría de Cultura</option>
                  <option value="sec-desarrollo">Secretaría de Desarrollo Económico</option>
                  <option value="all">👑 ALCALDE (Ver Todas las Secretarías)</option>
                </select>
             </div>

             <div className="p-4 bg-gov-blue-50/50 dark:bg-dark-accent/5 rounded-2xl border border-gov-blue-100 dark:border-dark-accent/10 flex items-center gap-3">
                <div className="p-2 bg-white dark:bg-dark-surface rounded-lg shadow-sm">
                   <Info size={16} className="text-gov-blue-600 dark:text-dark-cyan" />
                </div>
                <p className="text-[10px] text-gov-blue-800 dark:text-dark-muted leading-tight">
                  Al cambiar a <strong>Alcalde</strong>, el sistema desactivará los filtros de dependencia y te permitirá supervisar los {usuario?.idSecretaria === 'all' ? '100%' : '50%'} de tickets de la ciudad.
                </p>
             </div>
          </div>
        </div>

        <div className="mt-8 flex items-start gap-3 p-4 bg-gov-gray-50 dark:bg-dark-bg rounded-2xl border border-gov-gray-100 dark:border-dark-border">
          <Info size={16} className="text-gov-gray-400 shrink-0 mt-0.5" />
          <p className="text-[10px] text-gov-gray-500 dark:text-dark-muted leading-relaxed">
            Esta sección de simulación permite validar el comportamiento del CRM en diferentes escenarios jerárquicos durante el hackathon.
          </p>
        </div>
      </SettingsSection>

      {/* 3. SECCIÓN: APARIENCIA */}
      <SettingsSection 
        titulo="Apariencia y Visualización" 
        descripcion="Adapta la interfaz a tu entorno de trabajo actual"
        icono={<Palette size={22} />}
      >
        <div className="space-y-4">
           <p className="text-xs font-bold text-gov-gray-700 dark:text-dark-text uppercase tracking-widest">Tema de la interfaz</p>
           <ThemeToggle variant="card" />
           <p className="text-[11px] text-gov-gray-400 mt-4 italic">
             Consejo: El Modo Oscuro reduce la fatiga visual si trabajas en horarios nocturnos.
           </p>
        </div>
      </SettingsSection>

      {/* 4. SECCIÓN: NOTIFICACIONES */}
      <SettingsSection 
        titulo="Notificaciones y Alertas" 
        descripcion="Gestiona cómo recibes los avisos de urgencia legal"
        icono={<Bell size={22} />}
      >
        <div className="divide-y divide-gov-gray-50 dark:divide-dark-border">
           <ToggleRow 
             label="Alertas de tickets críticos" 
             desc="Mostrar banner rojo cuando hay tickets con menos de 3 días restantes" 
             active={notifConfig.criticos}
             onClick={() => setNotifConfig(prev => ({ ...prev, criticos: !prev.criticos }))}
           />
           <ToggleRow 
             label="Notificaciones de vencimiento" 
             desc="Mostrar campana con contador de tickets a punto de vencer en la barra superior" 
             active={notifConfig.vencimiento}
              onClick={() => setNotifConfig(prev => ({ ...prev, vencimiento: !prev.vencimiento }))}
           />
           <ToggleRow 
             label="Sonido de alerta" 
             desc="Reproducir pitido institucional al recibir un ticket clasificado como prioritario" 
             active={notifConfig.sonido}
             disabled
             onClick={() => {}}
           />
        </div>
      </SettingsSection>

      {/* 5. SECCIÓN: SEGURIDAD */}
      <SettingsSection 
        titulo="Seguridad y Acceso" 
        descripcion="Información técnica sobre tu sesión y permisos"
        icono={<Shield size={22} />}
      >
         <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <SecurityBadge label="Nivel de Acceso" value="Funcionario" />
            <SecurityBadge label="Región de Acceso" value="Medellín / Ts.net" />
            <SecurityBadge label="Protocolo RBAC" value="V3.2 Activo" />
         </div>
         <p className="mt-4 text-[10px] text-gov-gray-400 text-center">
           Tu sesión está cifrada mediante una red privada de Tailscale para protección de datos ciudadanos.
         </p>
      </SettingsSection>

      {/* 6. DANGER ZONE */}
      <div className="pt-4">
        <div className="bg-sem-red/5 dark:bg-sem-red/10 border-2 border-dashed border-sem-red/30 rounded-3xl p-8 space-y-6">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-sem-red text-white rounded-2xl shadow-lg shadow-sem-red/20">
              <AlertTriangle size={24} />
            </div>
            <div>
              <h2 className="text-lg font-black text-sem-red uppercase tracking-tight">Zona de Peligro (Presentación)</h2>
              <p className="text-xs text-sem-red/70 font-medium">Acciones irreversibles para limpieza de entorno</p>
            </div>
          </div>

          <div className="flex flex-col md:flex-row items-center justify-between gap-6 p-6 bg-white dark:bg-dark-surface rounded-2xl border border-sem-red/10">
            <div className="space-y-1">
              <p className="text-sm font-black text-gov-gray-900 dark:text-dark-text">Limpiar Base de Datos (DuckDB local)</p>
              <p className="text-xs text-gov-gray-500 dark:text-dark-muted max-w-sm">
                Elimina todos los tickets y registros actuales para iniciar una demostración desde cero. 
                <span className="font-bold text-sem-red italic"> Esta acción no se puede deshacer.</span>
              </p>
            </div>

            {showConfirmReset ? (
              <div className="flex gap-2 w-full md:w-auto">
                <button 
                  onClick={handleResetDB}
                  disabled={isResetting}
                  className="flex-1 md:flex-none px-6 py-3 bg-sem-red text-white text-xs font-black uppercase rounded-xl hover:bg-sem-red-dark transition-all animate-pulse"
                >
                  {isResetting ? 'Limpiando...' : '¡SÍ, ELIMINAR TODO!'}
                </button>
                <button 
                  onClick={() => setShowConfirmReset(false)}
                  className="flex-1 md:flex-none px-6 py-3 bg-gov-gray-100 dark:bg-dark-border text-gov-gray-600 dark:text-dark-muted text-xs font-black uppercase rounded-xl"
                >
                  Cancelar
                </button>
              </div>
            ) : (
              <button 
                onClick={() => setShowConfirmReset(true)}
                className="w-full md:w-auto flex items-center justify-center gap-2 px-8 py-3 bg-white dark:bg-dark-surface border-2 border-sem-red text-sem-red text-xs font-black uppercase rounded-xl hover:bg-sem-red hover:text-white transition-all group"
              >
                <Trash2 size={16} className="group-hover:rotate-12 transition-transform" />
                Vaciar Base de Datos
              </button>
            )}
          </div>
        </div>
      </div>

      {/* 6. CIERRE DE SESIÓN */}
      <div className="flex justify-center pt-8">
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-10 py-4 bg-sem-red/5 dark:bg-sem-red/10 border-2 border-sem-red/20 rounded-2xl text-sem-red font-black text-sm uppercase tracking-widest hover:bg-sem-red hover:text-white transition-all duration-300 shadow-lg shadow-sem-red/10"
        >
          <LogOut size={20} />
          Finalizar Sesión Operativa
        </button>
      </div>
    </div>
  );
}

/** Componentes Atómicos para la página */

function ReadOnlyField({ label, value, icon }: { label: string, value: string, icon?: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <p className="text-[10px] font-black text-gov-gray-400 uppercase tracking-widest">{label}</p>
      <div className="flex items-center gap-2 px-4 py-3 bg-gov-gray-50/50 dark:bg-dark-bg border border-gov-gray-100 dark:border-dark-border rounded-xl">
        {icon && <span className="text-gov-gray-400">{icon}</span>}
        <span className="text-sm font-bold text-gov-gray-700 dark:text-dark-text">{value}</span>
      </div>
    </div>
  );
}

function ToggleRow({ label, desc, active, onClick, disabled }: { label: string, desc: string, active: boolean, onClick: () => void, disabled?: boolean }) {
  return (
    <div className={cn(
      "flex items-center justify-between py-4 group transition-opacity",
      disabled && "opacity-50"
    )}>
      <div className="space-y-0.5">
        <div className="flex items-center gap-3">
          <p className="text-sm font-bold text-gov-gray-900 dark:text-dark-text">{label}</p>
          {disabled && (
            <span className="px-1.5 py-0.5 bg-gov-gray-100 dark:bg-dark-border text-[8px] font-black text-gov-gray-500 rounded uppercase">Próximamente</span>
          )}
        </div>
        <p className="text-xs text-gov-gray-500 dark:text-dark-muted max-w-sm">{desc}</p>
      </div>
      
      <button 
        onClick={onClick}
        disabled={disabled}
        className={cn(
          "w-12 h-6 rounded-full transition-colors relative",
          active ? "bg-gov-blue-700" : "bg-gov-gray-200 dark:bg-dark-border",
          disabled && "cursor-not-allowed"
        )}
      >
        <div className={cn(
          "absolute top-1 left-1 w-4 h-4 bg-white rounded-full transition-all shadow-md",
          active ? "translate-x-6" : "translate-x-0"
        )} />
      </button>
    </div>
  );
}

function SecurityBadge({ label, value }: { label: string, value: string }) {
  return (
    <div className="p-4 bg-gov-gray-50 dark:bg-dark-bg border border-gov-gray-100 dark:border-dark-border rounded-2xl flex flex-col items-center justify-center text-center space-y-1">
      <p className="text-[9px] font-black text-gov-gray-400 uppercase tracking-tighter">{label}</p>
      <p className="text-xs font-bold text-gov-blue-700 dark:text-dark-cyan">{value}</p>
    </div>
  );
}
