'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { adminService } from '@/services/adminService';
import SettingsSection from '@/components/settings/SettingsSection';
import { FolderPlus } from 'lucide-react';

export default function NewProjectPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [id, setId] = useState('');
  const [source, setSource] = useState('industries/business_standard');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const finish = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await adminService.createTemplate(id.trim(), source);
      router.push(`/templates/${r.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-3xl font-black dark:text-dark-text">Nuevo proyecto</h1>
      <p className="text-sm text-gov-gray-500 mb-6">Wizard — clonar plantilla base</p>

      <SettingsSection
        titulo={`Paso ${step} de 2`}
        descripcion={step === 1 ? 'Identificador del worker' : 'Resumen'}
        icono={<FolderPlus size={22} />}
      >
        {step === 1 && (
          <div className="space-y-4 max-w-md">
            <label className="block text-sm font-bold">Worker ID</label>
            <input
              value={id}
              onChange={(e) => setId(e.target.value)}
              className="w-full px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-bg font-mono"
              placeholder="mi-worker"
            />
            <label className="block text-sm font-bold">Plantilla origen</label>
            <input
              value={source}
              onChange={(e) => setSource(e.target.value)}
              className="w-full px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-bg font-mono text-sm"
            />
            <button
              type="button"
              onClick={() => setStep(2)}
              disabled={!id.trim()}
              className="px-4 py-2 bg-gov-blue-700 text-white rounded-xl text-sm font-bold disabled:opacity-50"
            >
              Siguiente
            </button>
          </div>
        )}
        {step === 2 && (
          <div className="space-y-4">
            <p className="text-sm">
              Crear <strong className="font-mono">{id}</strong> desde{' '}
              <strong className="font-mono">{source}</strong>
            </p>
            {error && <p className="text-red-600 text-sm">{error}</p>}
            <WizardActions
              onBack={() => setStep(1)}
              onFinish={finish}
              loading={loading}
            />
          </div>
        )}
      </SettingsSection>
    </div>
  );
}

function WizardActions({
  onBack,
  onFinish,
  loading,
}: {
  onBack: () => void;
  onFinish: () => void;
  loading: boolean;
}) {
  return (
    <div className="flex gap-2">
      <button type="button" onClick={onBack} className="px-4 py-2 border rounded-xl text-sm">
        Atrás
      </button>
      <button
        type="button"
        onClick={onFinish}
        disabled={loading}
        className="px-4 py-2 bg-gov-blue-700 text-white rounded-xl text-sm font-bold"
      >
        {loading ? 'Creando…' : 'Crear proyecto'}
      </button>
    </div>
  );
}
