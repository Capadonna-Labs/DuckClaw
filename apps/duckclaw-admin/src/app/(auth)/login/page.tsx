'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Loader2, ShieldCheck, Eye, EyeOff, Mail, Lock, AlertCircle } from 'lucide-react';
import { adminPostAuthPath, useAuthStore } from '@/store/authStore';
import { DEV_HINT_EMAIL, DEV_LOGIN_HINT_ENABLED } from '@/config/adminUsers';

const loginSchema = z.object({
  email: z.string().email('Email inválido'),
  password: z.string().min(8, 'Mínimo 8 caracteres'),
});

type LoginForm = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const router = useRouter();
  const { loginWithCredentials, isAuthenticated, isLoading, loginError, hasHydrated } =
    useAuthStore();
  const [showPassword, setShowPassword] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors },
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  });

  useEffect(() => {
    if (hasHydrated && isAuthenticated) router.replace('/overview');
  }, [hasHydrated, isAuthenticated, router]);

  const onSubmit = async (data: LoginForm) => {
    setLocalError(null);
    await loginWithCredentials(data.email, data.password);
    if (useAuthStore.getState().isAuthenticated) {
      const { returnTo: saved } = useAuthStore.getState();
      useAuthStore.getState().setReturnTo(null);
      router.replace(adminPostAuthPath(saved));
    }
  };

  const displayError =
    localError || loginError || errors.email?.message || errors.password?.message;

  return (
    <div className="min-h-screen w-full flex flex-col items-center justify-center p-4 sm:p-6">
      <div className="w-full max-w-md p-8 rounded-3xl bg-white text-slate-900 border border-slate-200 shadow-2xl">
        <header className="text-center space-y-2 mb-8">
          <div className="mx-auto w-14 h-14 rounded-2xl bg-gov-blue-700 text-white flex items-center justify-center text-2xl">
            🦆
          </div>
          <h1 className="text-2xl font-black">DuckClaw Admin</h1>
          <p className="text-sm text-slate-500 flex items-center justify-center gap-2">
            <ShieldCheck size={16} className="text-gov-blue-600" />
            Consola de configuración
          </p>
        </header>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
          <label className="block space-y-2">
            <span className="text-xs font-bold uppercase text-slate-500">Correo</span>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
              <input
                type="email"
                {...register('email')}
                className="w-full pl-10 pr-4 py-3 rounded-xl border border-slate-300 bg-white"
                autoComplete="username"
              />
            </div>
          </label>

          <label className="block space-y-2">
            <span className="text-xs font-bold uppercase text-slate-500">Contraseña</span>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
              <input
                type={showPassword ? 'text' : 'password'}
                {...register('password')}
                className="w-full pl-10 pr-12 py-3 rounded-xl border border-slate-300 bg-white"
                autoComplete="current-password"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400"
                aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </label>

          {displayError && (
            <p className="flex items-center gap-2 text-sm text-red-600 bg-red-50 p-3 rounded-xl">
              <AlertCircle size={16} />
              {displayError}
            </p>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-3 rounded-xl bg-gov-blue-700 text-white font-bold flex justify-center gap-2 disabled:opacity-60"
          >
            {isLoading ? <Loader2 size={18} className="animate-spin" /> : null}
            {isLoading ? 'Entrando…' : 'Entrar'}
          </button>
        </form>
      </div>

      {DEV_LOGIN_HINT_ENABLED && DEV_HINT_EMAIL && (
        <section className="mt-6 w-full max-w-md rounded-2xl border border-slate-700 bg-slate-800/80 p-4 text-sm text-slate-200">
          <p className="font-bold mb-2">Dev hint</p>
          <p className="text-xs text-slate-400 mb-2">
            Credenciales en <code className="font-mono">.env.local</code> (
            DUCKCLAW_ADMIN_EMAIL / DUCKCLAW_ADMIN_PASSWORD)
          </p>
          <button
            type="button"
            onClick={() => setValue('email', DEV_HINT_EMAIL)}
            className="text-xs font-bold px-3 py-1.5 rounded-lg bg-gov-blue-700 text-white"
          >
            Usar {DEV_HINT_EMAIL}
          </button>
        </section>
      )}
    </div>
  );
}
