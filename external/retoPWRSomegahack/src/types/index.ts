/** 
 * TIPOS DE UNIÓN Y ENUMERACIONES (The Lexicon)
 */

/** Estados posibles de un ticket PQRSD según la normativa colombiana */
export type TicketEstado = 'Pendiente' | 'En_Revision' | 'Resuelto';

/** Tipos de solicitud PQRSD */
export type TipoSolicitud = 'Peticion' | 'Queja' | 'Reclamo' | 'Sugerencia' | 'Denuncia';

/** Canal de ingreso del PQRSD */
export type CanalOrigen = 'WhatsApp' | 'Email' | 'Twitter' | 'Facebook' | 'Presencial' | 'Web';

/** Nivel de urgencia calculado por el frontend (NO viene del backend) */
export type NivelUrgencia = 'seguro' | 'atencion' | 'critico';


/** 
 * INTERFACE PRINCIPAL: Ticket
 * 
 * Mapeo del esquema DuckDB (snake_case) a camelCase para el frontend.
 * DB fields: id_ticket, tipo_solicitud, id_secretaria, fecha_creacion, 
 *            fecha_limite, estado, contenido_raw, resumen_ia, respuesta_sugerida,
 *            canal_origen, nombre_ciudadano
 */
export interface Ticket {
  /** Identificador único del ticket. PK en DuckDB (UUID or String) */
  idTicket: string;
  
  /** Categoría de la solicitud según normatividad */
  tipoSolicitud: TipoSolicitud;
  
  /** FK a la tabla secretarias en DuckDB */
  idSecretaria: string;
  
  /** ISO 8601 string. Viene de DuckDB como TIMESTAMP */
  fechaCreacion: string;
  
  /** ISO 8601 string. Deadline legal: fechaCreacion + 15 días hábiles */
  fechaLimite: string;
  
  /** Estado actual en el ciclo de vida del PQRSD */
  estado: TicketEstado;
  
  /** Texto raw tal como llegó del canal de origen (WhatsApp, email, etc.) */
  contenidoRaw: string;
  
  /** Resumen generado por IA del backend (es null si el procesamiento está pendiente) */
  resumenIa: string | null;
  
  /** Borrador de respuesta sugerido por la IA del backend según precedentes */
  respuestaSugerida: string | null;
  
  /** Plataforma por la cual se capturó el PQRSD */
  canalOrigen: CanalOrigen;
  
  /** Nombre del remitente o ciudadano que interpone la solicitud */
  nombreCiudadano: string;

  /** Documento de identidad del ciudadano (CC, NIT, Pasaporte, etc.) */
  documentoCiudadano?: string | null;

  /** Teléfono de contacto del ciudadano */
  telefonoCiudadano?: string | null;

  /** Título o asunto de la solicitud (especialmente para Email) */
  asunto?: string;

  /**
   * Número de radicado oficial — Formato: MDE-YYYYMMDD-NNNNNN-COD
   * Identificador legal principal. Generado en el backend (DuckDB) al ingreso.
   * En los mocks del frontend lo generamos con la función de radicado.ts
   * Mapeado desde: numero_radicado (snake_case en FastAPI/DuckDB)
   */
  numeroRadicado: string;

  /**
   * Email del ciudadano para notificaciones SMTP.
   * null = solicitud anónima (Decreto 1166 de 2016 — es un caso legal válido).
   * Mapeado desde: email_ciudadano (snake_case en FastAPI/DuckDB)
   */
  emailCiudadano: string | null;
}


/**
 * Ticket enriquecido por el frontend con campos calculados.
 * NUNCA se persiste en el backend. Es solo para la UI.
 */
export interface TicketConUrgencia extends Ticket {
  /** Días hábiles restantes calculados por el frontend utilizando date-fns */
  diasRestantes: number;
  
  /** Clasificación visual de urgencia según los días restantes */
  nivelUrgencia: NivelUrgencia;
}


/** 
 * INTERFACE: Secretaria
 * Definición de las dependencias administrativas del Distrito.
 */
export interface Secretaria {
  idSecretaria: string;
  nombre: string;
  /** Color HEX institucional para identificar visualmente la secretaría en la UI */
  colorIdentificador: string;
}


/** 
 * INTERFACE: Usuario (Funcionario Público)
 * Representa al usuario autenticado en la plataforma.
 */
export interface Usuario {
  idUsuario: string;
  nombreCompleto: string;
  cargo: string;
  /** FK a secretarias. Define el scope de datos que el usuario puede ver (RBAC) */
  idSecretaria: string;
  secretariaNombre: string;
  /** Rol del usuario para permisos adicionales */
  rol: 'admin' | 'funcionario' | 'alcalde';
  /** Iniciales para el avatar (ej: "CA" para "Carlos Arturo") */
  initials: string;
}


/**
 * INTERFACES DE API (The Communication Contract)
 */

/** Estructura estándar de respuesta para servicios de datos */
export interface ApiResponse<T> {
  data: T;
  total: number;
  /** Timestamp de la respuesta en formato ISO 8601 */
  timestamp: string;
  /** Mensaje de error descriptivo en caso de falla */
  error?: string;
}


/** Estructura para la gestión de filtros en la bandeja de entrada */
export interface TicketsFilter {
  estado?: TicketEstado | 'Todos';
  tipoSolicitud?: TipoSolicitud | 'Todos';
  nivelUrgencia?: NivelUrgencia | 'Todos';
  searchQuery?: string;
}

// ─── MÓDULO SMTP ────────────────────────────────────────

export type EstadoEmail = 'pendiente' | 'enviado' | 'fallido' | 'simulado';
export type TipoEmail   = 'confirmacion_radicado' | 'respuesta_oficial';

/**
 * Registro de un correo enviado o intentado.
 * Se almacenará en DuckDB cuando el backend lo soporte.
 * Por ahora se gestiona en memoria de sesión en el frontend.
 */
export interface RegistroEmail {
  idRegistro:      string;
  idTicket:        string;
  numeroRadicado:  string;
  tipoEmail:       TipoEmail;
  destinatario:    string;
  asunto:          string;
  fechaEnvio:      string;   // ISO 8601
  estado:          EstadoEmail;
  errorMensaje?:   string;
  messageId?:      string;   // ID del servidor SMTP para trazabilidad
}

/** Payload que el cliente envía a POST /api/email/confirmar */
export interface ConfirmacionEmailPayload {
  idTicket:             string;
  numeroRadicado:       string;
  emailCiudadano:       string;
  nombreCiudadano:      string;
  tipoSolicitud:        TipoSolicitud;   // ya existe en tus tipos
  secretariaNombre:     string;
  fechaLimiteRespuesta: string;          // ISO 8601
}

/** Payload que el cliente envía a POST /api/email/responder */
export interface RespuestaEmailPayload {
  idTicket:          string;
  numeroRadicado:    string;
  emailCiudadano:    string;
  nombreCiudadano:   string;
  tipoSolicitud:     TipoSolicitud;
  secretariaNombre:  string;
  nombreFuncionario: string;
  cargoFuncionario:  string;
  textoRespuesta:    string;
  fechaRespuesta:    string;   // ISO 8601
}

/** Resultado unificado de cualquier operación de envío de email */
export interface EmailSendResult {
  success:   boolean;
  messageId?: string;
  simulado:  boolean;
  registro:  RegistroEmail;
  error?:    string;
}
