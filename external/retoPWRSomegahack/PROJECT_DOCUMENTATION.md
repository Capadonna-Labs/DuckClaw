# 📘 CRM PQRSD - Alcaldía de Medellín (Proyecto Piloto OmegaHack 2026)

## 📌 1. Descripción General del Proyecto
**CRM PQRSD** es una plataforma centralizada diseñada para los funcionarios públicos pertenecientes a las diferentes secretarías de la **Alcaldía de Medellín (Distrito de Ciencia, Tecnología e Innovación)**. 

El propósito de la aplicación es modernizar y optimizar la gestión de **Peticiones, Quejas, Reclamos, Sugerencias y Denuncias (PQRSDs)** emitidas por los ciudadanos, consolidando solicitudes de canales ómnicanal bajo una misma interfaz inteligente. La plataforma asiste la toma de decisiones utilizando flujos eficientes, un panel de inteligencia artificial y tableros gerenciales.

---

## 🛠 2. Arquitectura y Stack Tecnológico
El proyecto se construyó bajo un enfoque moderno y seguro en el ecosistema Frontend:
- **Framework Principal:** Next.js 14 (App Router) en TypeScript.
- **Estilos e Interfaz:** Tailwind CSS (con un sistema de diseño institucional Medellín GovTech incorporado). Soporte total para **Modo Claro / Modo Oscuro**.
- **Gestión de Estado Centralizado:** Zustand (para autenticación simulada y manejo de filtros compartidos).
- **Tablero Ágil:** `@dnd-kit` para implementar vistas operativas (drag & drop).
- **Graficación Analítica:** Recharts para tableros gerenciales.
- **Inteligencia Artificial:** Conexión vía stream (Server Server-Sent Events o Proxy HTTP API) a OpenRouter para asistencia redactora de respuestas burocráticas.
- **Manejo de Fechas:** `date-fns` para cálculo preciso del semáforo legal (días faltantes/resolución).

---

## 🔐 3. Flujo de Autenticación y Seguridad (RBAC)
Actualmente operando en **Modo Piloto**, el sistema no solicita contraseña para facilitar pruebas del jurado o auditores, pero implementa internamente el patrón de **Role-Based Access Control (RBAC)**.
- **Selector de Funcionario**: El usuario elige un rol simulado (ej. *Profesional Universitario - Secretaría de Salud*).
- **Aislamiento de Datos por Secretaría**: Al iniciarse la sesión, la plataforma inyecta el `idSecretaria` del usuario. A partir de este momento, **absolutamente todos** los filtros, analíticas y bandejas de entrada quedan restringidos a los tickets que le pertenecen a esa dependencia específica (no se ven tickets de Educación desde la cuenta de Salud).
- En el despliegue final, el login apuntará al Directorio Activo (AD).

---

## 📥 4. Bandeja de Entrada (Dashboard Operativo)
Es el "Command Center" del funcionario. Presenta las PQRSD estructuradas.

### 4.1. Semáforo de Urgencia Legal
Cumpliendo con la Ley 1755 de 2015 sobre el derecho de petición, cada ticket calcula su fecha de vencimiento.
- **🔴 Crítico (Rojo):** Vence en 3 días o menos, o ya está vencido.
- **🟡 Atención (Oro/Amarillo):** Vence entre 4 y 10 días límite. 
- **🟢 Seguro (Verde):** Tiene más de 10 días para su desarrollo.

### 4.2. Vistas Duales (Tabla y Kanban)
- **Vista de Tabla (Modo Analítico):** Tabla tradicional de gestión masiva. Permite una lectura y validación rápida de fechas, identificadores de canal, remitentes y estado legal.
- **Vista Kanban (Modo Operacional):** Un tablero de arrastrar y soltar (Drag & Drop) segmentado en tres columnas (`Pendiente`, `En Revisión`, `Resuelto`). Facilita organizar cargas de trabajo sin refrescar la página. Actualiza los estados de manera nativa emulada.

### 4.3. Filtros Avanzados
En la parte superior, los funcionarios pueden refinar la búsqueda:
- **Barra de Texto:** Buscar por información dentro del cuerpo del mensaje o nombre del ciudadano.
- **Segmentaciones:** Filtra directamente por Tipos (Queja vs Reclamo), Estado (Resuelto) y Urgencia (Crítico).

---

## 📑 5. Detalle de PQRSD y Asistente de Inteligencia Artificial
Al seleccionar un ticket específico, el usuario entra a una vista completa con tres columnas o pilares:

1. **Detalles del Expediente:** Visualización omnicanal (Twitter, Email, WhatsApp) destacando remitente, radicado y las etiquetas PQRSD asociadas. 
2. **Editor de Respuesta Burocrática:** Un área rica para desarrollar el fallo gubernamental del caso, dotado con formato de texto institucional (simulado) para formalizar la salida. Al guardarlo se emite una mutación que resuelve el ticket.
3. **PQRSD-Assistant (Panel de IA):**
   - Panel anclado en la vista de escritorio que, basándose en el cuerpo crudo de la queja del ciudadano, evalúa e infiere una sugerencia de resolución técnica apropiada. 
   - Transmite respuesta por un flujo iterativo (Streaming AI), simulando una consulta sofisticada con protocolos RAG o directrices de la Alcaldía. Su propósito es acortar el tiempo empleado redactando respuestas estándar.

---

## 📈 6. Módulo de Analíticas y Reportes Institucionales
Un panel de inteligencia de negocios para nivel táctico (Supervisores y Directores de Dependencia). La página no usa información quemada al azar, sino que ejecuta **operaciones de agregación real** sobre el array de tickets activos de la secretaría autenticada, gracias al hook `useAnalytics.ts`.

### 6.1. Tarjetas Superiores (KPIs Generales)
- **Total Tickets:** Volumen absoluto de peticiones de la secretaría.
- **Tasa de Cumplimiento:** Porcentaje del total de boletos que se han resuelto a tiempo (sin estatus Crítico/Vencido). El objetivo del gobierno municipal es maximizar esta cifra. 
- **Tickets Críticos:** El número de radicados a riesgo de romper la norma de vencimiento legal municipal. 
- **Promedio de Respuesta:** Días promedio que ha tardado la oficina en pasar tickets a "Resuelto".

### 6.2. Gráfico: Tendencia de Gestión (Semanas) - Barras Agrupadas
- **Qué representa:** Cruza temporalmente dos grandes flujos: ¿Cuántos radican los ciudadanos contra cuántos resuelve el despacho? 
- **Interpretación del Gráfico:** 
   - **Barras Azules (Ingresados):** Refleja la cantidad de nuevas tareas para esa semana.
   - **Barras Verdes (Resueltos):** Muestra el desempeño o velocidad de despacho del área operativa.
   - *Nota de gestión:* Si consistentemente las barras azules son más altas que las verdes, indica que la secretaría padece un embudo de atención ("bottleneck") y está acumulando mora general.

### 6.3. Gráfico: Distribución por Tipo - Donut/Pastel
- **Qué representa:** Realiza el cálculo del peso o cuota que tienen las Peticiones, Quejas, Reclamos o Denuncias sobre el Total de Volumen entrante.
- **Interpretación del Gráfico:** 
  - Proporciona un desglose macro. Si predomina la porción etiquetada como *Queja* o *Reclamo*, es indicativo de problemas de calidad en los servicios provistos por la dependencia. Si son en su mayoría *Peticiones*, se valora como alto flujo de diligencias habituales pero sin crisis social asociada.

### 6.4. Gráfico: Volumen por Canal de Origen - Barras Horizontales
- **Qué representa:** Agrupa el volumen demográfico basándose en la ventanilla digital o física donde ingresó la solicitud (WhatsApp, Twitter, Web Institucional, PQRS presencial, etc).
- **Interpretación del Gráfico:**
  - Indica dónde ocurren los picos de contacto. Permite que Secretaría de Comunicaciones o Talento Humano enfoquen el aumento de capacidades. Si el canal dominante es sorpresivamente Twitter en lugar de la Web, significa que los ciudadanos prefieren escrachar por medios externos ante alguna ineficiencia local o inaccesibilidad de la página institucional.

---

## ⚙️ 7. Módulo de Configuración y Personalización
Los ajustes locales y estéticos de la plataforma.
- **Theme Toggle (Luz/Oscuro):** Un switch elaborado que no solo hace reír a Tailwind en modificar colores, sino que sincroniza el `ThemeProvider` global para que los componentes UI muten a grises satélites, azul marino oscuro (`#0D1117`) o colores limpios (`#ffffff`).
- Panel simulado para importes, exportación de bases de datos a CSV general y zonas de peligro de reseteo.

---

## 🔗 8. Condición Técnica (Handover para el Backend)
Todo el sistema está estructurado bajo **"Adaptadores"** dentro del directorio `src/services/`.
1. Físicamente no hay lógica incrustada en las Vistas (todo ocurre por inyección local). 
2. `ticketService.ts` opera bajo demoras simuladas (`setTimeout`) controlando `mockData.ts` para proveer los datos falsos y poder hacer el despliegue con éxito. 
3. Toda petición tiene un comentario explícito (`// HANDOVER AL BACKEND`) que enseña las rutas HTTP `(REST GET/PUT/PATCH)` y los parámetros exactos que deberá interconectar el futuro responsable (ej. DuckDB, FastAPI).
4. El sistema está limpio de advertencias (Warnings) de compilado y es completamente tipado (TypeScript StrictMode).
