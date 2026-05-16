# 🚀 Backend Implementation Guide - CRM PQRSD (Medellín Distrito)

Este documento es la **Guía Maestra para el Backend Developer**. Contiene absolutamente todo lo que debes implementar para conectar tu backend (DuckDB, FastAPI, Express, etc.) al actual frontend en Next.js. El frontend ya está preparado con comentarios en los servicios y las integraciones listas para ser reemplazadas.

---

## 📌 1. Checklist de Integración

Todos los llamados a la API del backend se encuentran aislados en un solo archivo en el frontend:
👉 **Ruta:** `src/services/ticketService.ts`

**Tus tareas:**
1. Crear el servidor API y asegurarte de que atienda peticiones CORS desde el dominio del frontend.
2. Definir tu Base de Datos en DuckDB basándote en los esquemas y tipos requeridos (Ver Sección 2).
3. Construir los 4 Endpoints esenciales (Ver Sección 3).
4. El Frontend maneja el "Role-Based Access Control" enviándote el `idSecretaria` del usuario. Tu backend **SIEMPRE** debe cruzar este ID para evitar filtrar información cruzada entre secretarías.
5. Reemplazar los cuerpos simulados (`setTimeout` y `TICKETS_MOCK`) de cada función en `ticketService.ts` por tu propio proxy de red (`fetch` o `axios`) usando tu `NEXT_PUBLIC_API_URL`.

---

## 💾 2. Esquema de Base de Datos en DuckDB

El frontend utiliza CamelCase para el estado interno de la UI, pero **DuckDB usa estándares SQL en `snake_case`**. 
Aquí tienes la sintaxis exacta de DuckDB para crear tus tablas iniciales:

```sql
CREATE SEQUENCE seq_ticket_id START 1;

CREATE TABLE secretarias (
    id_secretaria VARCHAR PRIMARY KEY,
    nombre VARCHAR NOT NULL,
    color_identificador VARCHAR NOT NULL
);

CREATE TABLE tickets (
    id_ticket VARCHAR PRIMARY KEY DEFAULT ('TK-' || LPAD(nextval('seq_ticket_id')::VARCHAR, 3, '0')),
    tipo_solicitud VARCHAR CHECK (tipo_solicitud IN ('Peticion', 'Queja', 'Reclamo', 'Sugerencia', 'Denuncia')),
    id_secretaria VARCHAR REFERENCES secretarias(id_secretaria),
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_limite TIMESTAMP, -- Generalmente fecha_creacion + INTERVAL 15 DAYS
    estado VARCHAR CHECK (estado IN ('Pendiente', 'En_Revision', 'Resuelto')) DEFAULT 'Pendiente',
    contenido_raw TEXT,
    resumen_ia TEXT,
    respuesta_sugerida TEXT,
    canal_origen VARCHAR CHECK (canal_origen IN ('WhatsApp', 'Email', 'Twitter', 'Facebook', 'Presencial', 'Web')),
    nombre_ciudadano VARCHAR
);
```

### Tabla Principal: `Tickets` (Mapeo Frontend-DuckDB)
Representa una PQRSD registrada.

| Campo (Frontend JSON) | Tipo (Backend/DB) | Consideraciones |
|-----------------------|-------------------|-----------------|
| `idTicket` | UUID / Varchar | Identificador único del ticket. |
| `tipoSolicitud` | Enum / String | `'Peticion' \| 'Queja' \| 'Reclamo' \| 'Sugerencia' \| 'Denuncia'` |
| `idSecretaria` | Varchar | FK a tabla Secretarias. |
| `fechaCreacion` | Config. Datetime / ISO 8601 | Ejemplo: `"2025-05-18T10:00:00Z"`. |
| `fechaLimite` | Config. Datetime / ISO 8601 | `fechaCreacion + 15 días hábiles`. |
| `estado` | Enum / String | `'Pendiente' \| 'En_Revision' \| 'Resuelto'` |
| `contenidoRaw` | Text | Cuerpo original del mensaje o PQRSD. |
| `resumenIa` | Text / Nulo | Puede estar en Null si aún no se procesa. |
| `respuestaSugerida` | Text / Nulo | Borrador del fallo/respuesta final. |
| `canalOrigen` | Enum / String | `'WhatsApp' \| 'Email' \| 'Twitter' \| 'Facebook' \| 'Presencial' \| 'Web'` |
| `nombreCiudadano` | Varchar | Nombre del solicitante. |

*Nota: La urgencia (Seguro, Atención, Crítico) se calcula implícitamente en el frontend usando `fechaLimite` y `date-fns`, **no tienes que guardarla en base de datos**.*

### Tabla Secundaria: `Secretarias`

| Campo (Frontend JSON) | Tipo (Backend/DB) | Consideraciones |
|-----------------------|-------------------|-----------------|
| `idSecretaria` | UUID / Varchar | Identificador único de dependencia. |
| `nombre` | Varchar | Ej: "Secretaría de Educación". |
| `colorIdentificador` | Varchar | HEX Code (Ej: `"#3B82F6"`). |

---

## 📡 3. Desarrollo de Endpoints (Rutas API)

Todos tus endpoints deberán envolver la respuesta en un wrapper estandarizado que el frontend espera leer:
```json
{
  "data": <Objeto_o_Array>,
  "total": <Conteo_entero>,
  "timestamp": "2026-04-18T18:00:00Z"
}
```

A continuación, los 4 endpoints primarios.

### 🔹 1. Obtener Secretaría por ID y Filtros (Bandeja de Entrada / Dashboard)
**Ruta:** `GET /api/tickets`

**Query Parameters (Obligatorios y Opcionales):**
- `idSecretaria` (string, **Requerido**): El ID de la secretaría del usuario logueado.
- `estado` (string, opcional): Filtrará por estado.
- `tipoSolicitud` (string, opcional): Filtrará por tipo.
- `search` (string, opcional): Buscar coincidencia en `nombreCiudadano` o `contenidoRaw`.

**Reglas de Negocio en DuckDB:**
Debes ejecutar una query como la siguiente desde Python (`duckdb`):
```python
import duckdb

def get_tickets(id_secretaria, estado=None, search=None):
    query = "SELECT * FROM tickets WHERE id_secretaria = ?"
    params = [id_secretaria]
    
    if estado and estado != "Todos":
        query += " AND estado = ?"
        params.append(estado)
        
    if search:
        query += " AND (LOWER(nombre_ciudadano) LIKE ? OR LOWER(contenido_raw) LIKE ?)"
        wildcard = f"%{search.lower()}%"
        params.extend([wildcard, wildcard])
        
    # Retornar como diccionarios transformando el snake_case en camelCase para la subred de JSON
    return duckdb.execute(query, params).pl().to_dicts() # Usando polars u otro motor
```

**Respuesta Exitosa (200 OK):**
```json
{
  "data": [ { "idTicket": "TK-001", "tipoSolicitud": "Queja", ... } ],
  "total": 1,
  "timestamp": "2026-04-18T18:00:00.000Z"
}
```

---

### 🔹 2. Obtener Detalle de Ticket Único
**Ruta:** `GET /api/tickets/{idTicket}`

**Query Parameters:**
- `idSecretariaUsuario` (string, **Requerido**): ID para validar que el Funcionario puede ver esto.

**Reglas de Negocio:**
Debes hacer `SELECT * FROM tickets WHERE id_ticket = :idTicket`. Si el ticket retornado no tiene el mismo `idSecretaria` que recibe el Query Param, debes devolver HTTP 403 o una respuesta con el objeto `error: "ACCESO_DENEGADO"`.

**Respuesta Exitosa (200 OK):**
```json
{
  "data": { "idTicket": "TK-001", "estado": "Pendiente", "contenidoRaw": "...", ... },
  "total": 1,
  "timestamp": "..."
}
```

---

### 🔹 3. Actualizar Estado / Enviar Respuesta de Resolución
**Ruta:** `PUT /api/tickets/{idTicket}/responder`
*(También se puede utilizar para la columna Kanban "drag and drop" simplemente omitiendo la respuesta y mandando el estado).*

**Headers:** `Content-Type: application/json`

**Body Enviado por el Frontend:**
```json
{
  "respuestaFinal": "Estimado ciudadano, se ha verificado el alcantarillado...",
  "idSecretariaUsuario": "sec-educacion"
}
```
*(Nota operativa: Si es drag & dop desde Kanban, el frontend mandará un body que diga `estado: 'En_Revision'`).*

**Reglas de Negocio:**
- Verificar que el usuario tenga acceso a ese ticket a través del `idSecretariaUsuario`.
- Realizar el UPDATE en la Base de Datos guardando la respuesta y alterando la columna `estado = 'Resuelto'`.

**Respuesta Exitosa (200 OK):**
```json
{
  "data": { "success": true },
  "total": 1,
  "timestamp": "..."
}
```

---

### 🔹 4. Cargar Catálogo de Secretarías
**Ruta:** `GET /api/secretarias`

Provee el catálogo que llena selectores o la validación del login real.

**Respuesta Exitosa (200 OK):**
```json
{
  "data": [
    { "idSecretaria": "educacion", "nombre": "Secretaría de Educación", "colorIdentificador": "#1E3A8A" },
    { "idSecretaria": "salud", "nombre": "Secretaría de Salud", "colorIdentificador": "#047857" }
  ],
  "total": 2,
  "timestamp": "..."
}
```

---

## 🤖 4. Integración de IA (Opcional para el Backend)
Actualmente, el Frontend maneja un proxy interno (`src/app/api/ia/regenerar/route.ts`) usando `OpenRouter` configurado con LLMs como Sonnet o Gemini para responder a los ciudadanos usando Server-Sent Events (SSE) y Streaming (lo que dota al UI de la experiencia ChatGPT de escritura).

Si decides que el Backend intercepte y realice la lógica RAG completa o indexación vectorial (conectando con tu propio Python local o base DuckDB vectorizada), solo deberás reemplazar la ruta `api/ia/regenerar` del Frontend y apuntar tu lógica para que envíe los chunks SSE o directamente la cadena redactada. Manten la respuesta de redacción en Markdown para que el widget `ResponseEditor.tsx` lo lea correctamente.

¡Éxito armando el cerebro de la aplicación! 🧠 Todo el frente está diseñado para recibir JSONs directos y es extremadamente resistente.
