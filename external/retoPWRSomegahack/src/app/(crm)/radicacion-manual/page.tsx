'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { 
  FilePlus, 
  Trash2, 
  Send, 
  User, 
  Mail, 
  Phone, 
  Tag, 
  MessageSquare,
  Plus,
  Loader2,
  CheckCircle2,
  ShieldCheck,
  Building
} from 'lucide-react';

interface ManualTicketForm {
  id: string; // ID temporal para manejo de estado
  nombreCiudadano: string;
  documento: string;
  emailCiudadano: string;
  telefono: string;
  tipoSolicitud: string;
  idSecretaria: string;
  asunto: string;
  contenidoRaw: string;
}

const SECRETARIAS = [
  { id: 'sec-salud', label: 'Salud' },
  { id: 'sec-educacion', label: 'Educación' },
  { id: 'sec-movilidad', label: 'Movilidad' },
  { id: 'sec-cultura', label: 'Cultura' },
  { id: 'sec-desarrollo', label: 'Desarrollo Económico' },
];

const CATEGORIAS = ['Peticion', 'Queja', 'Reclamo', 'Sugerencia', 'Denuncia'];

export default function RadicacionManualPage() {
  const router = useRouter();
  const [tickets, setTickets] = useState<ManualTicketForm[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [successCount, setSuccessCount] = useState<number | null>(null);

  // Añadir un nuevo formulario vacío a la lista
  const addTicket = () => {
    const newTicket: ManualTicketForm = {
      id: Math.random().toString(36).substr(2, 9),
      nombreCiudadano: '',
      documento: '',
      emailCiudadano: '',
      telefono: '',
      tipoSolicitud: 'Peticion',
      idSecretaria: 'sec-salud',
      asunto: '',
      contenidoRaw: '',
    };
    setTickets([...tickets, newTicket]);
    setSuccessCount(null);
  };

  // Eliminar un ticket de la lista
  const removeTicket = (id: string) => {
    setTickets(tickets.filter(t => t.id !== id));
  };

  // Actualizar campo de un ticket específico
  const updateTicket = (id: string, field: keyof ManualTicketForm, value: string) => {
    setTickets(tickets.map(t => t.id === id ? { ...t, [field]: value } : t));
  };

  // Enviar todos los tickets al servidor
  const handleSubmitAll = async () => {
    if (tickets.length === 0) return;

    // Validación básica de emails antes de enviar
    for (const t of tickets) {
      if (t.emailCiudadano && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(t.emailCiudadano.trim())) {
        alert(`El email "${t.emailCiudadano}" no tiene un formato válido.`);
        return;
      }
    }
    
    setIsSubmitting(true);
    try {
      const response = await fetch('/api/tickets/batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tickets }),
      });

      if (!response.ok) throw new Error('Error al enviar el lote');

      const result = await response.json();
      setSuccessCount(result.created);
      setTickets([]); // Limpiar lista
      
      // Opcional: Redirigir después de unos segundos
      setTimeout(() => {
        router.push('/dashboard');
      }, 3000);

    } catch (err) {
      console.error(err);
      alert('Hubo un error al procesar la radicación. Por favor intente de nuevo.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-8 animate-in fade-in duration-500">
      {/* ── ENCABEZADO ── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <h1 className="text-3xl font-black text-gov-gray-900 dark:text-dark-text tracking-tight uppercase italic flex items-center gap-3">
            <div className="w-10 h-10 bg-gov-blue-700 dark:bg-dark-accent rounded-xl flex items-center justify-center text-white shrink-0">
              <FilePlus size={24} />
            </div>
            Radicación Manual
          </h1>
          <p className="text-sm text-gov-gray-500 dark:text-dark-muted font-medium mt-1">
            Gestión de solicitudes recibidas en formato físico o presencial.
          </p>
        </div>

        {tickets.length > 0 && (
          <button
            onClick={handleSubmitAll}
            disabled={isSubmitting}
            className="flex items-center justify-center gap-3 px-8 py-4 bg-sem-green hover:bg-sem-green-hover text-white rounded-2xl font-black uppercase tracking-widest text-xs shadow-lg shadow-sem-green/20 transition-all hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 disabled:scale-100"
          >
            {isSubmitting ? (
              <Loader2 className="animate-spin" size={18} />
            ) : (
              <Send size={18} />
            )}
            Radicar {tickets.length} {tickets.length === 1 ? 'Solicitud' : 'Solicitudes'}
          </button>
        )}
      </div>

      {/* ── ESTADO DE ÉXITO ── */}
      {successCount !== null && (
        <div className="bg-sem-green/10 border border-sem-green/20 rounded-2xl p-8 flex flex-col items-center text-center space-y-4 animate-in zoom-in-95 duration-300">
          <div className="w-16 h-16 bg-sem-green text-white rounded-full flex items-center justify-center shadow-lg shadow-sem-green/30">
            <CheckCircle2 size={32} />
          </div>
          <div className="space-y-1">
            <h2 className="text-xl font-bold text-sem-green uppercase tracking-wide">¡Radicación Exitosa!</h2>
            <p className="text-sm text-gov-gray-600 dark:text-dark-muted">
              Se han creado <strong>{successCount}</strong> tickets correctamente en la base de datos DuckDB (pqrsd_crm).
              Redirigiendo a la bandeja de entrada...
            </p>
          </div>
        </div>
      )}

      {/* ── LISTA DE FORMULARIOS ── */}
      <div className="space-y-6">
        {tickets.map((form, index) => (
          <div 
            key={form.id} 
            className="bg-white dark:bg-dark-surface border border-gov-gray-100 dark:border-dark-border rounded-3xl shadow-xl shadow-gov-blue-900/5 overflow-hidden animate-in slide-in-from-bottom-4 duration-500"
            style={{ animationDelay: `${index * 100}ms` }}
          >
            {/* Header del Formulario */}
            <div className="bg-gov-gray-50 dark:bg-dark-bg px-6 py-4 border-b border-gov-gray-100 dark:border-dark-border flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="w-8 h-8 bg-gov-blue-100 dark:bg-dark-accent/20 text-gov-blue-700 dark:text-dark-cyan rounded-lg flex items-center justify-center text-sm font-black">
                  {index + 1}
                </span>
                <span className="text-xs font-bold text-gov-gray-500 dark:text-dark-muted uppercase tracking-widest">
                  Nuevo Registro Físico
                </span>
              </div>
              <button 
                onClick={() => removeTicket(form.id)}
                className="p-2 text-gov-gray-400 hover:text-sem-red transition-colors"
                title="Eliminar este formulario"
              >
                <Trash2 size={18} />
              </button>
            </div>

            {/* Cuerpo del Formulario */}
            <div className="p-8 grid grid-cols-1 md:grid-cols-2 gap-8">
              {/* Columna Izquierda: Ciudadano */}
              <div className="space-y-6">
                <div className="flex items-center gap-2 text-gov-blue-700 dark:text-dark-cyan font-bold uppercase text-[10px] tracking-widest border-b border-gov-blue-100 dark:border-dark-border pb-2">
                  <User size={12} /> Datos del Ciudadano
                </div>
                
                <div className="space-y-4">
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-black text-gov-gray-400 dark:text-dark-muted uppercase ml-1">Nombre Completo</label>
                    <div className="relative group">
                      <User size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-gov-gray-300 group-focus-within:text-gov-blue-500 transition-colors" />
                      <input 
                        type="text"
                        placeholder="Ej: Juan Pérez"
                        className="w-full pl-11 pr-4 py-3 bg-gov-gray-50 dark:bg-dark-bg border border-gov-gray-200 dark:border-dark-border rounded-xl text-sm focus:ring-2 focus:ring-gov-blue-500 transition-all outline-none"
                        value={form.nombreCiudadano}
                        onChange={(e) => updateTicket(form.id, 'nombreCiudadano', e.target.value)}
                      />
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-[10px] font-black text-gov-gray-400 dark:text-dark-muted uppercase ml-1">Número de Documento</label>
                    <div className="relative group">
                      <ShieldCheck size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-gov-gray-300 group-focus-within:text-gov-blue-500 transition-colors" />
                      <input 
                        type="text"
                        placeholder="CC / NIT / Pasaporte"
                        className="w-full pl-11 pr-4 py-3 bg-gov-gray-50 dark:bg-dark-bg border border-gov-gray-200 dark:border-dark-border rounded-xl text-sm focus:ring-2 focus:ring-gov-blue-500 transition-all outline-none"
                        value={form.documento}
                        onChange={(e) => updateTicket(form.id, 'documento', e.target.value)}
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <label className="text-[10px] font-black text-gov-gray-400 dark:text-dark-muted uppercase ml-1">Correo Electrónico</label>
                      <div className="relative group">
                        <Mail size={16} className={`absolute left-4 top-1/2 -translate-y-1/2 transition-colors ${
                          form.emailCiudadano && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.emailCiudadano.trim())
                            ? 'text-sem-red'
                            : 'text-gov-gray-300 group-focus-within:text-gov-blue-500'
                        }`} />
                        <input 
                          type="email"
                          placeholder="ciudadano@email.com"
                          className={`w-full pl-11 pr-4 py-3 bg-gov-gray-50 dark:bg-dark-bg border rounded-xl text-sm focus:ring-2 transition-all outline-none ${
                            form.emailCiudadano && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.emailCiudadano.trim())
                              ? 'border-sem-red focus:ring-sem-red/20'
                              : 'border-gov-gray-200 dark:border-dark-border focus:ring-gov-blue-500'
                          }`}
                          value={form.emailCiudadano}
                          onChange={(e) => updateTicket(form.id, 'emailCiudadano', e.target.value)}
                        />
                      </div>
                      {form.emailCiudadano && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.emailCiudadano.trim()) && (
                        <p className="text-[9px] text-sem-red font-bold uppercase mt-1 ml-1 animate-pulse">Formato de email inválido</p>
                      )}
                    </div>
                    <div className="space-y-1.5">
                      <label className="text-[10px] font-black text-gov-gray-400 dark:text-dark-muted uppercase ml-1">Teléfono</label>
                      <div className="relative group">
                        <Phone size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-gov-gray-300 group-focus-within:text-gov-blue-500 transition-colors" />
                        <input 
                          type="text"
                          placeholder="300 000 0000"
                          className="w-full pl-11 pr-4 py-3 bg-gov-gray-50 dark:bg-dark-bg border border-gov-gray-200 dark:border-dark-border rounded-xl text-sm focus:ring-2 focus:ring-gov-blue-500 transition-all outline-none"
                          value={form.telefono}
                          onChange={(e) => updateTicket(form.id, 'telefono', e.target.value)}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Columna Derecha: El Caso */}
              <div className="space-y-6">
                <div className="flex items-center gap-2 text-gov-blue-700 dark:text-dark-cyan font-bold uppercase text-[10px] tracking-widest border-b border-gov-blue-100 dark:border-dark-border pb-2">
                  <Tag size={12} /> Detalles de la Solicitud
                </div>

                <div className="space-y-4">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <label className="text-[10px] font-black text-gov-gray-400 dark:text-dark-muted uppercase ml-1">Tipo de Trámite</label>
                      <div className="relative group">
                        <Tag size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-gov-gray-300" />
                        <select 
                          className="w-full pl-11 pr-4 py-3 bg-gov-gray-50 dark:bg-dark-bg border border-gov-gray-200 dark:border-dark-border rounded-xl text-sm focus:ring-2 focus:ring-gov-blue-500 appearance-none outline-none"
                          value={form.tipoSolicitud}
                          onChange={(e) => updateTicket(form.id, 'tipoSolicitud', e.target.value)}
                        >
                          {CATEGORIAS.map(c => <option key={c} value={c}>{c}</option>)}
                        </select>
                      </div>
                    </div>
                    <div className="space-y-1.5">
                      <label className="text-[10px] font-black text-gov-gray-400 dark:text-dark-muted uppercase ml-1">Secretaría</label>
                      <div className="relative group">
                        <Building size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-gov-gray-300" />
                        <select 
                          className="w-full pl-11 pr-4 py-3 bg-gov-gray-50 dark:bg-dark-bg border border-gov-gray-200 dark:border-dark-border rounded-xl text-sm focus:ring-2 focus:ring-gov-blue-500 appearance-none outline-none"
                          value={form.idSecretaria}
                          onChange={(e) => updateTicket(form.id, 'idSecretaria', e.target.value)}
                        >
                          {SECRETARIAS.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
                        </select>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-[10px] font-black text-gov-gray-400 dark:text-dark-muted uppercase ml-1">Asunto de la Solicitud</label>
                    <div className="relative group">
                      <MessageSquare size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-gov-gray-300 group-focus-within:text-gov-blue-500 transition-colors" />
                      <input 
                        type="text"
                        placeholder="Resumen corto del caso"
                        className="w-full pl-11 pr-4 py-3 bg-gov-gray-50 dark:bg-dark-bg border border-gov-gray-200 dark:border-dark-border rounded-xl text-sm focus:ring-2 focus:ring-gov-blue-500 transition-all outline-none"
                        value={form.asunto}
                        onChange={(e) => updateTicket(form.id, 'asunto', e.target.value)}
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* Contenido (Ancho Completo) */}
              <div className="md:col-span-2 space-y-1.5">
                <label className="text-[10px] font-black text-gov-gray-400 dark:text-dark-muted uppercase ml-1">Descripción Detallada del Caso</label>
                <textarea 
                  rows={4}
                  placeholder="Escriba aquí el contenido del documento físico..."
                  className="w-full p-5 bg-gov-gray-50 dark:bg-dark-bg border border-gov-gray-200 dark:border-dark-border rounded-2xl text-sm focus:ring-2 focus:ring-gov-blue-500 transition-all outline-none resize-none leading-relaxed"
                  value={form.contenidoRaw}
                  onChange={(e) => updateTicket(form.id, 'contenidoRaw', e.target.value)}
                />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* ── BOTONES DE ACCIÓN ── */}
      <div className="flex flex-col items-center justify-center gap-6 py-10">
        <button 
          onClick={addTicket}
          disabled={isSubmitting}
          className="group flex flex-col items-center gap-3 p-8 border-2 border-dashed border-gov-blue-200 dark:border-dark-border rounded-[2.5rem] hover:border-gov-blue-500 hover:bg-gov-blue-50/50 dark:hover:bg-dark-accent/10 transition-all w-full max-w-sm"
        >
          <div className="w-14 h-14 bg-white dark:bg-dark-surface border-2 border-gov-blue-500 text-gov-blue-500 rounded-2xl flex items-center justify-center group-hover:scale-110 transition-transform shadow-lg shadow-gov-blue-900/10">
            <Plus size={28} />
          </div>
          <div className="text-center">
            <p className="font-black text-gov-gray-900 dark:text-dark-text uppercase tracking-widest text-xs">Crear un nuevo ticket</p>
            <p className="text-[10px] text-gov-gray-400 dark:text-dark-muted font-bold mt-1 uppercase tracking-tighter">Añade otro registro físico al lote</p>
          </div>
        </button>

        {tickets.length > 0 && (
          <div className="flex items-center gap-4 bg-gov-blue-900 text-white px-6 py-3 rounded-2xl shadow-2xl animate-in slide-in-from-bottom-2">
            <ShieldCheck className="text-gov-cyan-400" size={20} />
            <p className="text-xs font-bold uppercase tracking-widest">
              Lote de <span className="text-gov-cyan-400">{tickets.length}</span> registros listo para persistir
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
