import { addBusinessDays, subBusinessDays, formatISO } from 'date-fns';
import { 
  Secretaria, 
  Usuario, 
  Ticket
} from '@/types';
import { generarNumeroRadicado } from '@/lib/radicado';

const hoy = new Date();

// --- SECRETARÍAS MOCK ---
export const SECRETARIAS_MOCK: Secretaria[] = [
  { idSecretaria: 'sec-salud',       nombre: 'Secretaría de Salud',                 colorIdentificador: '#0057B8' },
  { idSecretaria: 'sec-educacion',   nombre: 'Secretaría de Educación',             colorIdentificador: '#00875A' },
  { idSecretaria: 'sec-movilidad',   nombre: 'Secretaría de Movilidad',             colorIdentificador: '#D97706' },
  { idSecretaria: 'sec-cultura',     nombre: 'Secretaría de Cultura',               colorIdentificador: '#7C3AED' },
  { idSecretaria: 'sec-desarrollo',  nombre: 'Secretaría de Desarrollo Económico',  colorIdentificador: '#DC2626' },
];

// Memoria para hilos de conversación (Continuidad)
export const MEMORIA_HILOS_MOCK: Record<string, { asunto: string, cuerpoOriginal: string, nombre?: string, fecha?: Date }> = {};

// --- USUARIOS MOCK ---
export const USUARIOS_MOCK: Usuario[] = [
  {
    idUsuario: 'usr-001',
    nombreCompleto: 'María Camila Restrepo',
    cargo: 'Profesional Universitario',
    idSecretaria: 'sec-salud',
    secretariaNombre: 'Secretaría de Salud',
    rol: 'admin',
    initials: 'MC',
  },
  {
    idUsuario: 'usr-002',
    nombreCompleto: 'Juan Felipe Gaviria',
    cargo: 'Analista de Sistemas',
    idSecretaria: 'sec-educacion',
    secretariaNombre: 'Secretaría de Educación',
    rol: 'funcionario',
    initials: 'JG',
  },
  {
    idUsuario: 'usr-003',
    nombreCompleto: 'Andrés Felipe Correa',
    cargo: 'Coordinador Técnico',
    idSecretaria: 'sec-movilidad',
    secretariaNombre: 'Secretaría de Movilidad',
    rol: 'funcionario',
    initials: 'AC',
  },
  {
    idUsuario: 'usr-004',
    nombreCompleto: 'Liliana Patricia Ortiz',
    cargo: 'Especialista en PQRSD',
    idSecretaria: 'sec-cultura',
    secretariaNombre: 'Secretaría de Cultura',
    rol: 'funcionario',
    initials: 'LO',
  },
];

// --- TICKETS MOCK ---
export const TICKETS_MOCK: Ticket[] = [
  // --- SECRETARÍA DE SALUD (6 tickets con distribución de urgencia) ---
  {
    idTicket: 'TK-001',
    tipoSolicitud: 'Queja',
    idSecretaria: 'sec-salud',
    fechaCreacion: formatISO(subBusinessDays(hoy, 13)),
    fechaLimite: formatISO(addBusinessDays(hoy, 2)), // Nivel CRÍTICO
    estado: 'Pendiente',
    contenidoRaw: 'Buenos días, estoy intentando pedir una cita para medicina general en el centro de salud de Aranjuez y me dicen que no hay agenda disponible hasta dentro de 3 meses. Esto es inaceptable para un paciente hipertenso.',
    resumenIa: 'Ciudadano reporta falta de agenda para cita médica prioritaria (hipertensión) en Aranjuez con demora de 3 meses.',
    respuestaSugerida: 'Cordial saludo. Se ha coordinado con la red prestadora de Aranjuez para habilitar un cupo prioritario. Por favor asista el próximo martes a las 10:00 AM.',
    canalOrigen: 'WhatsApp',
    asunto: 'Solicitud PQRSD', nombreCiudadano: 'Jose Orlando Duque',
    numeroRadicado: generarNumeroRadicado('sec-salud', subBusinessDays(hoy, 13)),
    emailCiudadano: 'j.duque@gmail.com',
  },
  {
    idTicket: 'TK-002',
    tipoSolicitud: 'Peticion',
    idSecretaria: 'sec-salud',
    fechaCreacion: formatISO(subBusinessDays(hoy, 14)),
    fechaLimite: formatISO(addBusinessDays(hoy, 1)), // Nivel CRÍTICO
    estado: 'En_Revision',
    contenidoRaw: 'Solicito formalmente el suministro de los insumos de insulina para mi hijo de 8 años, ya que en la farmacia de la EPS me dicen que están agotados hace una semana.',
    resumenIa: 'Petición urgente de suministro de insulina para menor de edad debido a desabastecimiento en farmacia EPS.',
    respuestaSugerida: 'Estimado ciudadano, se ha verificado el stock y se autoriza la entrega inmediata en la farmacia alterna ubicada en el Edificio Comedal.',
    canalOrigen: 'Email',
    asunto: 'Solicitud PQRSD', nombreCiudadano: 'Claudia Marcela Jaramillo',
    numeroRadicado: generarNumeroRadicado('sec-salud', subBusinessDays(hoy, 14)),
    emailCiudadano: 'cmarcela.jaramillo@hotmail.com',
  },
  {
    idTicket: 'TK-003',
    tipoSolicitud: 'Reclamo',
    idSecretaria: 'sec-salud',
    fechaCreacion: formatISO(subBusinessDays(hoy, 9)),
    fechaLimite: formatISO(addBusinessDays(hoy, 6)), // Nivel ATENCIÓN
    estado: 'Pendiente',
    contenidoRaw: 'El servicio de urgencias de la Clínica León XIII está colapsado. Llevo 5 horas esperando con mi madre que tiene dolor abdominal agudo y nadie nos da información.',
    resumenIa: 'Reclamo por tiempos de espera excesivos (5 horas) en urgencias de Clínica León XIII para paciente con dolor agudo.',
    respuestaSugerida: 'Se ha remitido el caso al equipo de auditoría para verificar el cumplimiento del Triage en la Clínica León XIII y agilizar la atención de su familiar.',
    canalOrigen: 'Twitter',
    asunto: 'Solicitud PQRSD', nombreCiudadano: 'Sebastián Restrepo',
    numeroRadicado: generarNumeroRadicado('sec-salud', subBusinessDays(hoy, 9)),
    emailCiudadano: 'srestrepo@outlook.com',
  },
  {
    idTicket: 'TK-004',
    tipoSolicitud: 'Sugerencia',
    idSecretaria: 'sec-salud',
    fechaCreacion: formatISO(subBusinessDays(hoy, 8)),
    fechaLimite: formatISO(addBusinessDays(hoy, 7)), // Nivel ATENCIÓN
    estado: 'Pendiente',
    contenidoRaw: 'Sería muy útil que en la página de la Alcaldía podamos ver en tiempo real la ocupación de las camas UCI de las diferentes clínicas de la ciudad.',
    resumenIa: 'Sugerencia de implementar un tablero de control público sobre ocupación de camas UCI en tiempo real.',
    respuestaSugerida: 'Agradecemos su valioso aporte. Actualmente contamos con el portal MEVA donde se publica información epidemiológica que incluiremos en futuras actualizaciones.',
    canalOrigen: 'Web',
    asunto: 'Solicitud PQRSD', nombreCiudadano: 'Laura Sofía Méndez',
    numeroRadicado: generarNumeroRadicado('sec-salud', subBusinessDays(hoy, 8)),
    emailCiudadano: 'laura.mendez@yahoo.com',
  },
  {
    idTicket: 'TK-005',
    tipoSolicitud: 'Peticion',
    idSecretaria: 'sec-salud',
    fechaCreacion: formatISO(subBusinessDays(hoy, 3)),
    fechaLimite: formatISO(addBusinessDays(hoy, 12)), // Nivel SEGURO
    estado: 'En_Revision',
    contenidoRaw: 'Solicito información sobre las jornadas de vacunación contra la fiebre amarilla para viajeros que se realizarán en el mes de mayo.',
    resumenIa: null, // IA aún no procesó
    respuestaSugerida: null,
    canalOrigen: 'Facebook',
    asunto: 'Solicitud PQRSD', nombreCiudadano: 'Carlos Mario Vélez',
    numeroRadicado: generarNumeroRadicado('sec-salud', subBusinessDays(hoy, 3)),
    emailCiudadano: 'cm.velez@une.net.co',
  },
  {
    idTicket: 'TK-006',
    tipoSolicitud: 'Denuncia',
    idSecretaria: 'sec-salud',
    fechaCreacion: formatISO(subBusinessDays(hoy, 2)),
    fechaLimite: formatISO(addBusinessDays(hoy, 13)), // Nivel SEGURO
    estado: 'Resuelto',
    contenidoRaw: 'Denuncio que en el restaurante del barrio Laureles están vendiendo alimentos con fecha de vencimiento alterada.',
    resumenIa: 'Denuncia ciudadana sobre presunta alteración de fechas de vencimiento en alimentos en establecimiento de Laureles.',
    respuestaSugerida: 'Se procedió a realizar visita de inspección técnica el día de ayer, resultando en el sellamiento temporal del establecimiento por motivos sanitarios.',
    canalOrigen: 'WhatsApp',
    asunto: 'Solicitud PQRSD', nombreCiudadano: 'Anonimo por seguridad',
    numeroRadicado: generarNumeroRadicado('sec-salud', subBusinessDays(hoy, 2)),
    emailCiudadano: 'denuncias.ciudadanas@gmail.com',
  },

  // --- OTRAS SECRETARÍAS (9 tickets adicionales para completar 15) ---
  {
    idTicket: 'TK-007',
    tipoSolicitud: 'Queja',
    idSecretaria: 'sec-movilidad',
    fechaCreacion: formatISO(subBusinessDays(hoy, 1)),
    fechaLimite: formatISO(addBusinessDays(hoy, 14)),
    estado: 'Pendiente',
    contenidoRaw: 'El semáforo de la 80 con la 30 está dañado y está generando un trancón monumental desde hace 2 horas.',
    resumenIa: null,
    respuestaSugerida: null,
    canalOrigen: 'Twitter',
    asunto: 'Solicitud PQRSD', nombreCiudadano: 'Ramiro Antonio Sosa',
    numeroRadicado: generarNumeroRadicado('sec-movilidad', subBusinessDays(hoy, 1)),
    emailCiudadano: 'ramiro.sosa@gmail.com',
  },
  {
    idTicket: 'TK-008',
    tipoSolicitud: 'Peticion',
    idSecretaria: 'sec-educacion',
    fechaCreacion: formatISO(subBusinessDays(hoy, 10)),
    fechaLimite: formatISO(addBusinessDays(hoy, 5)),
    estado: 'En_Revision',
    contenidoRaw: 'Necesito una copia de mi diploma de bachiller del Liceo Antioqueño del año 1995.',
    resumenIa: 'Solicitud de duplicado de diploma de bachiller de 1995 en institución pública.',
    respuestaSugerida: 'Su solicitud ha sido radicada. Por favor realice el pago de los derechos de trámite en la taquilla virtual para proceder con el envío digital.',
    canalOrigen: 'Email',
    asunto: 'Solicitud PQRSD', nombreCiudadano: 'Marta Nelly Rojas',
    numeroRadicado: generarNumeroRadicado('sec-educacion', subBusinessDays(hoy, 10)),
    emailCiudadano: 'marta.rojas@hotmail.com',
  },
  {
    idTicket: 'TK-009',
    tipoSolicitud: 'Reclamo',
    idSecretaria: 'sec-movilidad',
    fechaCreacion: formatISO(subBusinessDays(hoy, 5)),
    fechaLimite: formatISO(addBusinessDays(hoy, 10)),
    estado: 'Pendiente',
    contenidoRaw: 'Me pusieron una fotomulta en un lugar donde no hay señalización de velocidad. Exijo que se revise mi caso.',
    resumenIa: 'Reclamo por fotomulta alegando falta de señalización vial en el punto de captura.',
    respuestaSugerida: 'Se ha agendado una audiencia virtual de impugnación para que presente sus pruebas ante el inspector de tránsito.',
    canalOrigen: 'Web',
    asunto: 'Solicitud PQRSD', nombreCiudadano: 'Jorge Eliecer Gaitán',
    numeroRadicado: generarNumeroRadicado('sec-movilidad', subBusinessDays(hoy, 5)),
    emailCiudadano: null,
  },
  {
    idTicket: 'TK-010',
    tipoSolicitud: 'Peticion',
    idSecretaria: 'sec-cultura',
    fechaCreacion: formatISO(subBusinessDays(hoy, 1)),
    fechaLimite: formatISO(addBusinessDays(hoy, 14)),
    estado: 'Pendiente',
    contenidoRaw: '¿Cuáles son los requisitos para participar en la convocatoria de estímulos para artistas locales de este año?',
    resumenIa: null,
    respuestaSugerida: null,
    canalOrigen: 'Web',
    asunto: 'Solicitud PQRSD', nombreCiudadano: 'Valentina Zapata',
    numeroRadicado: generarNumeroRadicado('sec-cultura', subBusinessDays(hoy, 1)),
    emailCiudadano: 'valentina.zapata@outlook.com',
  },
  {
    idTicket: 'TK-011',
    tipoSolicitud: 'Sugerencia',
    idSecretaria: 'sec-educacion',
    fechaCreacion: formatISO(subBusinessDays(hoy, 4)),
    fechaLimite: formatISO(addBusinessDays(hoy, 11)),
    estado: 'Pendiente',
    contenidoRaw: 'Sugiero que incluyan clases de programación básica en todos los colegios públicos del Distrito desde primaria.',
    resumenIa: 'Propuesta educativa para incluir formación en programación desde el ciclo de básica primaria.',
    respuestaSugerida: 'Excelente iniciativa. Estamos trabajando en el programa "Medellín Valle del Software" que busca precisamente integrar estas competencias.',
    canalOrigen: 'Email',
    asunto: 'Solicitud PQRSD', nombreCiudadano: 'Federico Londoño',
    numeroRadicado: generarNumeroRadicado('sec-educacion', subBusinessDays(hoy, 4)),
    emailCiudadano: null,
  },
  {
    idTicket: 'TK-012',
    tipoSolicitud: 'Denuncia',
    idSecretaria: 'sec-movilidad',
    fechaCreacion: formatISO(subBusinessDays(hoy, 0)),
    fechaLimite: formatISO(addBusinessDays(hoy, 15)),
    estado: 'Pendiente',
    contenidoRaw: 'Hay unos carros mal parqueados en la acera de mi casa bloqueando la salida de mi garaje.',
    resumenIa: 'Denuncia por invasión de espacio público y bloqueo de salida privada por vehículos mal estacionados.',
    respuestaSugerida: 'Se ha generado la alerta a la patrulla de tránsito más cercana para proceder con el comparendo y retiro con grúa.',
    canalOrigen: 'WhatsApp',
    asunto: 'Solicitud PQRSD', nombreCiudadano: 'Beatriz Eugenia Pino',
    numeroRadicado: generarNumeroRadicado('sec-movilidad', subBusinessDays(hoy, 0)),
    emailCiudadano: 'beatriz.pino@gmail.com',
  },
  {
    idTicket: 'TK-013',
    tipoSolicitud: 'Queja',
    idSecretaria: 'sec-desarrollo',
    fechaCreacion: formatISO(subBusinessDays(hoy, 3)),
    fechaLimite: formatISO(addBusinessDays(hoy, 12)),
    estado: 'En_Revision',
    contenidoRaw: 'La feria de emprendimiento del parque de El Poblado estuvo muy mal organizada, los puestos estaban muy pegados.',
    resumenIa: 'Queja sobre logística y distanciamiento en evento comercial público del parque El Poblado.',
    respuestaSugerida: 'Lamentamos los inconvenientes. Se tomarán medidas correctivas en el diseño del layout para las próximas ferias del barrio.',
    canalOrigen: 'Facebook',
    asunto: 'Solicitud PQRSD', nombreCiudadano: 'Gustavo Adolfo Perez',
    numeroRadicado: generarNumeroRadicado('sec-desarrollo', subBusinessDays(hoy, 3)),
    emailCiudadano: null,
  },
  {
    idTicket: 'TK-014',
    tipoSolicitud: 'Peticion',
    idSecretaria: 'sec-cultura',
    fechaCreacion: formatISO(subBusinessDays(hoy, 2)),
    fechaLimite: formatISO(addBusinessDays(hoy, 13)),
    estado: 'Pendiente',
    contenidoRaw: 'Solicito el préstamo del teatro al aire libre de Pedregal para un evento cultural comunitario sin ánimo de lucro.',
    resumenIa: 'Solicitud de espacio cultural público para evento comunitario gratuito en el barrio Pedregal.',
    respuestaSugerida: 'La solicitud se encuentra en trámite de validación de disponibilidad de fechas. Le contactaremos en máximo 3 días hábiles.',
    canalOrigen: 'Web',
    asunto: 'Solicitud PQRSD', nombreCiudadano: 'Junta de Acción Comunal',
    numeroRadicado: generarNumeroRadicado('sec-cultura', subBusinessDays(hoy, 2)),
    emailCiudadano: null,
  },
  {
    idTicket: 'TK-015',
    tipoSolicitud: 'Reclamo',
    idSecretaria: 'sec-desarrollo',
    fechaCreacion: formatISO(subBusinessDays(hoy, 7)),
    fechaLimite: formatISO(addBusinessDays(hoy, 8)),
    estado: 'Pendiente',
    contenidoRaw: 'No me han llegado los incentivos del programa de apoyo a pequeños comerciantes a pesar de que cumplí con todos los requisitos.',
    resumenIa: 'Reclamo por incumplimiento en desembolso de subsidios para pequeños comerciantes.',
    respuestaSugerida: 'Se ha verificado que hubo un error en su cuenta bancaria registrada. Por favor actualice sus datos en la plataforma para realizar el pago.',
    canalOrigen: 'Email',
    asunto: 'Solicitud PQRSD', nombreCiudadano: 'Maria Eugenia Rojas',
    numeroRadicado: generarNumeroRadicado('sec-desarrollo', subBusinessDays(hoy, 7)),
    emailCiudadano: 'me.rojas@hotmail.com',
  },
];

export const DELAY_SIMULADO_MS = 800;

import type { RegistroEmail } from '@/types';

/** Historial de correos enviados (mock de sesión) */
export let REGISTROS_EMAIL_MOCK: RegistroEmail[] = [];

/** Añade un registro al historial en memoria */
export function agregarRegistroEmail(registro: RegistroEmail): void {
  REGISTROS_EMAIL_MOCK = [registro, ...REGISTROS_EMAIL_MOCK];
}

/** Obtiene el historial de un ticket específico */
export function getRegistrosEmailByTicket(idTicket: string): RegistroEmail[] {
  return REGISTROS_EMAIL_MOCK.filter(r => r.idTicket === idTicket);
}
