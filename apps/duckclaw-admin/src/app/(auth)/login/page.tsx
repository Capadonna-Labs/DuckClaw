'use client';

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Loader2, ShieldCheck, Eye, EyeOff, Mail, Lock, AlertCircle } from 'lucide-react';
import { adminPostAuthPath, useAuthStore } from '@/store/authStore';
import { DEV_HINT_EMAIL, DEV_LOGIN_HINT_ENABLED } from '@/config/adminUsers';

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryLoginAttempted = useRef(false);
  const { loginWithCredentials, isAuthenticated, isSubmitting, loginError, hasHydrated } =
    useAuthStore();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null);

  const redirectIfAuthed = useCallback(() => {
    if (useAuthStore.getState().isAuthenticated) {
      const { returnTo: saved } = useAuthStore.getState();
      useAuthStore.getState().setReturnTo(null);
      router.replace(adminPostAuthPath(saved));
    }
  }, [router]);

  useEffect(() => {
    if (hasHydrated && isAuthenticated) router.replace('/overview');
  }, [hasHydrated, isAuthenticated, router]);

  const submitLogin = useCallback(
    async (rawEmail: string, rawPassword: string) => {
      const em = rawEmail.trim();
      const pw = rawPassword;
      if (!em || !em.includes('@')) {
        setFieldError('Email inválido');
        return;
      }
      if (pw.length < 8) {
        setFieldError('Mínimo 8 caracteres');
        return;
      }
      setFieldError(null);
      await loginWithCredentials(em, pw);
      redirectIfAuthed();
    },
    [loginWithCredentials, redirectIfAuthed]
  );

  useEffect(() => {
    if (queryLoginAttempted.current) return;

    const qEmail = searchParams.get('email')?.trim() ?? '';
    const qPassword = searchParams.get('password') ?? '';
    if (qEmail) setEmail(qEmail);
    if (qPassword) setPassword(qPassword);
    if (!qEmail || !qPassword) return;

    queryLoginAttempted.current = true;
    if (typeof window !== 'undefined') {
      window.history.replaceState({}, '', '/login');
    }

    void submitLogin(qEmail, qPassword);
  }, [searchParams, submitLogin]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void submitLogin(email, password);
  };

  const displayError = fieldError || loginError;

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

        <form onSubmit={onSubmit} className="space-y-5">
          <div className="block space-y-2">
            <label htmlFor="login-email" className="text-xs font-bold uppercase text-slate-500">
              Correo
            </label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" size={18} />
              <input
                id="login-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full pl-10 pr-4 py-3 rounded-xl border border-slate-300 bg-white"
                autoComplete="username"
              />
            </div>
          </div>

          <div className="block space-y-2">
            <label htmlFor="login-password" className="text-xs font-bold uppercase text-slate-500">
              Contraseña
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" size={18} />
              <input
                id="login-password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full pl-10 pr-12 py-3 rounded-xl border border-slate-300 bg-white"
                autoComplete="current-password"
              />
              <button
                type="button"
                tabIndex={-1}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => setShowPassword((v) => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 z-10 p-1.5 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100"
                aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          {displayError && (
            <p className="flex items-center gap-2 text-sm text-red-600 bg-red-50 p-3 rounded-xl">
              <AlertCircle size={16} />
              {displayError}
            </p>
          )}

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full py-3 rounded-xl bg-gov-blue-700 text-white font-bold flex justify-center gap-2 disabled:opacity-60"
          >
            {isSubmitting ? <Loader2 size={18} className="animate-spin" /> : null}
            {isSubmitting ? 'Entrando…' : 'Entrar'}
          </button>
        </form>
      </div>

      {DEV_LOGIN_HINT_ENABLED && DEV_HINT_EMAIL && (
        <section className="mt-6 w-full max-w-md rounded-2xl border border-slate-700 bg-slate-800/80 p-4 text-sm text-slate-200">
          <p className="font-bold mb-2">Dev hint</p>
          <p className="text-xs text-slate-400 mb-2">
            Credenciales en <code className="font-mono">.env</code> (DUCKCLAW_ADMIN_EMAIL /
            DUCKCLAW_ADMIN_PASSWORD).
          </p>
          <button
            type="button"
            onClick={() => setEmail(DEV_HINT_EMAIL)}
            className="text-xs font-bold px-3 py-1.5 rounded-lg bg-gov-blue-700 text-white"
          >
            Usar {DEV_HINT_EMAIL}
          </button>
        </section>
      )}
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center">
          <Loader2 className="animate-spin text-gov-blue-700" size={32} />
        </div>
      }
    >
      <LoginForm />
    </Suspense>
  );
}
