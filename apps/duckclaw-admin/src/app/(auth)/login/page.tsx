'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2, ShieldCheck, Eye, EyeOff, Mail, Lock, AlertCircle, UserCircle } from 'lucide-react';
import { useAuthStore } from '@/store/authStore';
import { DEV_LOGIN_HINT } from '@/config/adminUsers';

export default function LoginPage() {
  const router = useRouter();
  const { loginWithCredentials, isAuthenticated, isLoading, loginError } = useAuthStore();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    if (isAuthenticated) router.replace('/overview');
  }, [isAuthenticated, router]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    if (!email.trim() || !password.trim()) {
      setLocalError('Completa correo y contraseña');
      return;
    }
    await loginWithCredentials(email, password);
    if (useAuthStore.getState().isAuthenticated) router.replace('/overview');
  };

  const fillDemo = (demoEmail: string, demoPassword: string) => {
    setEmail(demoEmail);
    setPassword(demoPassword);
    setLocalError(null);
  };

  const displayError = localError || loginError;

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

        <form onSubmit={handleLogin} className="space-y-5">
          <label className="block space-y-2">
            <span className="text-xs font-bold uppercase text-slate-500">Correo</span>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full pl-10 pr-4 py-3 rounded-xl border border-slate-300 bg-white"
                autoComplete="username"
              />
            </div>
          </label>

          <label className="block space-y-2">
            <span className="text-xs font-bold uppercase text-slate-500">Contraseña</span>
            <PasswordField
              password={password}
              setPassword={setPassword}
              showPassword={showPassword}
              setShowPassword={setShowPassword}
            />
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

      <DemoUsersPanel onSelect={fillDemo} />
    </div>
  );
}

function PasswordField({
  password,
  setPassword,
  showPassword,
  setShowPassword,
}: {
  password: string;
  setPassword: (v: string) => void;
  showPassword: boolean;
  setShowPassword: (v: boolean) => void;
}) {
  return (
    <div className="relative">
      <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
      <input
        type={showPassword ? 'text' : 'password'}
        value={password}
        onChange={(e) => setPassword(e.target.value)}
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
  );
}

function DemoUsersPanel({
  onSelect,
}: {
  onSelect: (email: string, password: string) => void;
}) {
  return (
    <section className="mt-6 w-full max-w-md rounded-2xl border border-slate-700 bg-slate-800/80 p-4 text-sm text-slate-200">
      <p className="font-bold flex items-center gap-2 mb-3">
        <UserCircle size={18} />
        Usuarios de prueba (desarrollo)
      </p>
      <ul className="space-y-2">
        {DEV_LOGIN_HINT.map((u) => (
          <li
            key={u.email}
            className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-900/50 px-3 py-2"
          >
            <div>
              <p className="font-mono text-xs text-gov-cyan-400">{u.email}</p>
              <p className="text-[11px] text-slate-400">
                rol: {u.rol} · pass: <span className="font-mono">{u.passwordHint}</span>
              </p>
            </div>
            <button
              type="button"
              onClick={() => onSelect(u.email, u.passwordHint)}
              className="text-xs font-bold px-3 py-1.5 rounded-lg bg-gov-blue-700 hover:bg-gov-blue-600 text-white"
            >
              Usar
            </button>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-[11px] text-slate-500">
        Para añadir usuarios edita{' '}
        <code className="text-slate-400">src/config/adminUsers.ts</code>
      </p>
    </section>
  );
}
