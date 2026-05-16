'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Building2, Loader2, ShieldCheck, Eye, EyeOff, Mail, Lock, AlertCircle } from 'lucide-react';
import { useAuthStore } from '@/store/authStore';

export default function LoginPage() {
  const router = useRouter();
  const { loginWithCredentials, isAuthenticated, isLoading, loginError } = useAuthStore();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  // Redirección si ya está autenticado
  useEffect(() => {
    if (isAuthenticated) {
      router.push('/dashboard');
    }
  }, [isAuthenticated, router]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);

    if (!email.trim() || !password.trim()) {
      setLocalError('Por favor completa todos los campos');
      return;
    }

    try {
      await loginWithCredentials(email, password);
      router.push('/dashboard');
    } catch {
      // El error ya lo maneja el store (loginError)
    }
  };

  const displayError = localError || loginError;

  return (
    <div className="min-h-screen relative flex items-center justify-center p-4 font-sans overflow-hidden bg-slate-900">
      {/* Background Gradients & Effects */}
      <div className="absolute inset-0 z-0">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px]"></div>
        <div className="absolute left-0 right-0 top-0 -z-10 m-auto h-[310px] w-[310px] rounded-full bg-gov-blue-600 opacity-20 blur-[100px]"></div>
        <div className="absolute bottom-0 right-0 -z-10 h-[400px] w-[400px] rounded-full bg-cyan-600 opacity-20 blur-[120px]"></div>
      </div>

      <div className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl border border-white/20 dark:border-slate-800/50 rounded-3xl shadow-2xl p-8 sm:p-10 w-full max-w-md space-y-8 animate-in fade-in zoom-in-95 duration-500 relative z-10">
        
        {/* CABECERA */}
        <div className="flex flex-col items-center text-center space-y-4">
          <div className="w-16 h-16 bg-gradient-to-br from-gov-blue-600 to-cyan-500 rounded-2xl flex items-center justify-center text-white shadow-lg shadow-gov-blue-500/30 transform transition-transform hover:scale-105 hover:rotate-3">
            <Building2 size={32} strokeWidth={1.5} />
          </div>
          <div>
            <h1 className="text-2xl font-black text-slate-900 dark:text-white tracking-tight">Alcaldía de Medellín</h1>
            <p className="text-[10px] text-gov-blue-600 dark:text-cyan-400 uppercase font-black tracking-[0.2em] mt-1">
              Distrito de Ciencia, Tecnología e Innovación
            </p>
          </div>
          
          <div className="w-full h-px bg-gradient-to-r from-transparent via-slate-200 dark:via-slate-700 to-transparent" />
          
          <h2 className="text-sm font-semibold text-slate-600 dark:text-slate-300 flex items-center gap-2">
            <ShieldCheck size={18} className="text-gov-blue-500" />
            Acceso Seguro CRM PQRSD
          </h2>
        </div>

        {/* FORMULARIO */}
        <form onSubmit={handleLogin} className="space-y-5">
          {/* Email */}
          <div className="space-y-2">
            <label htmlFor="login-email" className="text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider pl-1">
              Correo electrónico
            </label>
            <div className="relative group">
              <Mail size={18} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-gov-blue-500 transition-colors" />
              <input
                id="login-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="usuario@correo.com"
                autoComplete="email"
                className="w-full bg-slate-50/50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-2xl pl-11 pr-4 py-3.5 text-sm font-medium text-slate-900 dark:text-white focus:bg-white dark:focus:bg-slate-800 focus:ring-2 focus:ring-gov-blue-500/50 focus:border-gov-blue-500 outline-none transition-all placeholder:text-slate-400"
              />
            </div>
          </div>

          {/* Password */}
          <div className="space-y-2">
            <label htmlFor="login-password" className="text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider pl-1">
              Contraseña
            </label>
            <div className="relative group">
              <Lock size={18} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-gov-blue-500 transition-colors" />
              <input
                id="login-password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
                className="w-full bg-slate-50/50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-2xl pl-11 pr-12 py-3.5 text-sm font-medium text-slate-900 dark:text-white focus:bg-white dark:focus:bg-slate-800 focus:ring-2 focus:ring-gov-blue-500/50 focus:border-gov-blue-500 outline-none transition-all placeholder:text-slate-400"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors p-1"
                tabIndex={-1}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          {/* ERROR */}
          {displayError && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-500/30 rounded-xl p-3 text-xs font-bold text-red-600 dark:text-red-400 flex items-center gap-2 animate-in fade-in slide-in-from-top-2">
              <AlertCircle size={14} className="shrink-0" />
              {displayError}
            </div>
          )}

          {/* SUBMIT */}
          <button
            type="submit"
            disabled={isLoading}
            className="w-full bg-gradient-to-r from-gov-blue-600 to-cyan-600 hover:from-gov-blue-700 hover:to-cyan-700 text-white font-bold py-4 rounded-2xl shadow-lg shadow-gov-blue-500/25 transition-all hover:-translate-y-0.5 active:translate-y-0 flex items-center justify-center gap-3 disabled:opacity-70 disabled:cursor-not-allowed disabled:transform-none"
          >
            {isLoading ? (
              <>
                <Loader2 size={20} className="animate-spin" />
                Validando credenciales...
              </>
            ) : (
              'Ingresar al Sistema'
            )}
          </button>
        </form>

        {/* CREDENCIALES DE PRUEBA / AUTO-FILL */}
        <div className="pt-2">
          <div className="relative flex items-center py-4">
            <div className="flex-grow border-t border-slate-200 dark:border-slate-800"></div>
            <span className="flex-shrink-0 mx-4 text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">
              Acceso Rápido
            </span>
            <div className="flex-grow border-t border-slate-200 dark:border-slate-800"></div>
          </div>
          
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => {
                setEmail('test@rr.com');
                setPassword('test1234');
              }}
              className="flex flex-col items-center justify-center p-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white/50 dark:bg-slate-800/50 hover:bg-slate-50 dark:hover:bg-slate-800 hover:border-gov-blue-300 dark:hover:border-gov-blue-700 transition-all group"
            >
              <span className="text-xs font-bold text-slate-700 dark:text-slate-200 group-hover:text-gov-blue-600 dark:group-hover:text-cyan-400 transition-colors">Modo Demo</span>
              <span className="text-[10px] text-slate-500 mt-0.5">Mock Data offline</span>
            </button>
            <button
              type="button"
              onClick={() => {
                setEmail('rraliadosteam@gmail.com');
                setPassword('CRMadmin123');
              }}
              className="flex flex-col items-center justify-center p-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white/50 dark:bg-slate-800/50 hover:bg-slate-50 dark:hover:bg-slate-800 hover:border-cyan-300 dark:hover:border-cyan-700 transition-all group"
            >
              <span className="text-xs font-bold text-slate-700 dark:text-slate-200 group-hover:text-cyan-600 dark:group-hover:text-cyan-400 transition-colors">Modo Admin</span>
              <span className="text-[10px] text-slate-500 mt-0.5">DuckDB + API Routes</span>
            </button>
          </div>
        </div>

        {/* PIE DE PÁGINA */}
        <div className="pt-6 text-center">
          <p className="text-[10px] text-slate-400 dark:text-slate-500 font-medium">
            Desarrollado para Medellín Distrito Especial por OmegaHack 2026
          </p>
        </div>
      </div>
    </div>
  );
}
