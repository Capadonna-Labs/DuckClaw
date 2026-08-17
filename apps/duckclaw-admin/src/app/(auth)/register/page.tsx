'use client';

import Link from 'next/link';
import { FormEvent, useState } from 'react';
import { AlertCircle, CheckCircle2, Eye, EyeOff, Lock, Mail, ShieldCheck, UserRound } from 'lucide-react';

function apiError(data: unknown, fallback: string): string {
  if (data && typeof data === 'object' && typeof (data as { detail?: unknown }).detail === 'string') {
    return (data as { detail: string }).detail;
  }
  return fallback;
}

export default function RegisterPage() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail || !normalizedEmail.includes('@')) {
      setError('Introduce un correo válido.');
      return;
    }
    if (password.length < 8) {
      setError('La contraseña debe tener al menos 8 caracteres.');
      return;
    }
    if (password !== confirmPassword) {
      setError('Las contraseñas no coinciden.');
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const response = await fetch('/api/admin/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email: normalizedEmail, password, nombre: name.trim() }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setError(apiError(data, 'No se pudo crear la cuenta.'));
        return;
      }
      setCreated(true);
      setPassword('');
      setConfirmPassword('');
    } catch {
      setError('No se pudo conectar con el servidor.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen w-full flex items-center justify-center p-4 sm:p-6">
      <section className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-8 text-slate-900 shadow-2xl">
        <header className="mb-8 text-center space-y-2">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-gov-blue-700 text-2xl text-white">
            🦆
          </div>
          <h1 className="text-2xl font-black">Crear cuenta inicial</h1>
          <p className="flex items-center justify-center gap-2 text-sm text-slate-500">
            <ShieldCheck size={16} className="text-gov-blue-600" />
            Configura el administrador local de DuckClaw
          </p>
        </header>

        {created ? (
          <div className="space-y-5">
            <p className="flex gap-2 rounded-xl bg-green-50 p-4 text-sm text-green-800">
              <CheckCircle2 className="mt-0.5 shrink-0" size={18} />
              Cuenta creada. Espera unos segundos a que termine la escritura y entra con tus nuevas credenciales.
            </p>
            <Link
              href={`/login?email=${encodeURIComponent(email)}`}
              className="block w-full rounded-xl bg-gov-blue-700 py-3 text-center font-bold text-white"
            >
              Ir a iniciar sesión
            </Link>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-5">
            <p className="rounded-xl bg-slate-50 p-3 text-xs text-slate-600">
              Este registro solo está disponible antes de que exista una cuenta. Después, los administradores crean
              usuarios desde Accesos. En DuckClaw Desktop también actualiza el archivo local de credenciales.
            </p>
            <label className="block space-y-2">
              <span className="text-xs font-bold uppercase text-slate-500">Nombre</span>
              <div className="relative">
                <UserRound className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  className="w-full rounded-xl border border-slate-300 bg-white py-3 pl-10 pr-4"
                  autoComplete="name"
                  placeholder="Tu nombre"
                />
              </div>
            </label>
            <label className="block space-y-2">
              <span className="text-xs font-bold uppercase text-slate-500">Correo</span>
              <div className="relative">
                <Mail className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                <input
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className="w-full rounded-xl border border-slate-300 bg-white py-3 pl-10 pr-4"
                  autoComplete="username"
                  required
                />
              </div>
            </label>
            <label className="block space-y-2">
              <span className="text-xs font-bold uppercase text-slate-500">Contraseña</span>
              <div className="relative">
                <Lock className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="w-full rounded-xl border border-slate-300 bg-white py-3 pl-10 pr-12"
                  autoComplete="new-password"
                  minLength={8}
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((value) => !value)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-slate-500 hover:bg-slate-100"
                  aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </label>
            <label className="block space-y-2">
              <span className="text-xs font-bold uppercase text-slate-500">Repetir contraseña</span>
              <input
                type={showPassword ? 'text' : 'password'}
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3"
                autoComplete="new-password"
                minLength={8}
                required
              />
            </label>
            {error ? (
              <p role="alert" className="flex items-center gap-2 rounded-xl bg-red-50 p-3 text-sm text-red-600">
                <AlertCircle size={16} />
                {error}
              </p>
            ) : null}
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-xl bg-gov-blue-700 py-3 font-bold text-white disabled:opacity-60"
            >
              {busy ? 'Creando cuenta…' : 'Crear cuenta'}
            </button>
          </form>
        )}

        <p className="mt-6 text-center text-sm text-slate-500">
          ¿Ya tienes una cuenta?{' '}
          <Link href="/login" className="font-bold text-gov-blue-700 hover:underline">
            Iniciar sesión
          </Link>
        </p>
      </section>
    </main>
  );
}
