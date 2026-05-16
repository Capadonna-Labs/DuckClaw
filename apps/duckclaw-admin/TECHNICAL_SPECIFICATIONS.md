# Especificaciones Técnicas — CRM PQRSD Medellín (GovTech)

## 📌 Visión General
El **CRM PQRSD Medellín** es una plataforma de grado institucional diseñada para la gestión eficiente y transparente de Peticiones, Quejas, Reclamos, Sugerencias y Denuncias del Distrito de Medellín. El sistema integra Inteligencia Artificial para el análisis de urgencia y generación de respuestas, junto con un robusto módulo de comunicaciones SMTP para garantizar la trazabilidad legal de cada interacción con el ciudadano.

---

## 🛠️ Stack Tecnológico
- **Frontend**: Next.js 14 (App Router), React 18, TypeScript.
- **Estilos**: Tailwind CSS (Sistema de diseño institucional con paleta de colores del Distrito).
- **Estado Global**: Zustand (Auth, Gestión de Secretarías).
- **Comunicaciones**: Nodemailer (SMTP) con soporte para Strategy Pattern (Mock/Live).
- **IA**: Integración con OpenRouter (Modelo: `arcee-ai/trinity-large-preview:free`).
- **Iconografía**: Lucide React.
- **Fechas**: Date-fns (localización en español).

---

## 🏗️ Arquitectura del Sistema

### 1. Gestión de Radicados (Legalidad)
Cada ticket cuenta con un **Número de Radicado Oficial** generado bajo la normativa vigente (Ley 1755 de 2015).
- **Formato**: `MDE-YYYYMMDD-NNNNNN-COD`
- **Utilidad**: `src/lib/radicado.ts` maneja la generación, validación y formateo (compacto/completo).

### 2. Módulo de Comunicaciones SMTP
Implementado con un patrón **Strategy** en `src/services/emailService.ts` para permitir:
- **Modo Live**: Envío real a través de Gmail SMTP (App Passwords).
- **Modo Mock**: Simulación en desarrollo/demo que registra los correos en la terminal sin realizar el envío real.
- **Templates**: `src/lib/emailTemplates.ts` contiene diseños HTML con CSS inline, logos del Distrito y avisos legales (Decreto 1166/2016).

### 3. Motor de Inteligencia Artificial
- **Análisis de Urgencia**: Clasificación automática (Crítico, Atención, Seguro) basada en el contenido y la fecha límite.
- **Resumen Ejecutivo**: Generación dinámica de resúmenes de casos complejos.
- **Co-pilot de Respuesta**: Sugerencia de respuestas oficiales redactadas con lenguaje institucional inclusivo.

---

## 📋 Módulos y Funcionalidades Core

### 🎫 Gestión de Tickets (`/dashboard`)
- **Bandeja de Entrada**: Filtrado dinámico por Secretaría y búsqueda por radicado.
- **Indicadores de Urgencia**: Badges visuales que cambian de color según los días hábiles restantes.
- **Simulador de Demo**: Panel exclusivo para el hackathon que permite simular la entrada de un nuevo ticket y el envío inmediato del correo de confirmación.

### 📝 Detalle y Respuesta (`/ticket/[id]`)
- **Visualización Pro-Level**: Banner de radicado prominente con función de copiado.
- **Editor de Respuesta Oficial**:
    - Validación de longitud mínima (50 caracteres).
    - **ConfirmModal**: Modal de seguridad de doble paso para evitar envíos accidentales.
    - **Detección de Cambios**: Aviso visual de cambios sin guardar.
- **Email Status Tracker**: Historial de trazabilidad que muestra cada correo enviado al ciudadano para ese ticket específico.

---

## 🛣️ API Routes
- `POST /api/email/confirmar`: Dispara el correo de bienvenida y radicación.
- `POST /api/email/responder`: Envía la respuesta oficial firmada por el funcionario.
- `POST /api/ia/resumen-ejecutivo`: Interfaz con OpenRouter para el análisis de texto.

---

## 📊 Modelo de Datos (Types)
- **Ticket**: Extendido con metadatos de radicado, email del ciudadano y análisis de IA.
- **RegistroEmail**: Estructura para la trazabilidad (ID de mensaje, timestamp, tipo, estado).
- **Usuario**: Gestión de perfiles con roles (Admin/Funcionario) y asignación a Secretarías.

---

## ⚙️ Configuración de Entorno (.env.local)
```env
# IA
OPENROUTER_API_KEY=...
NEXT_PUBLIC_IA_HABILITADA=true

# SMTP
SMTP_MODE=live # o 'mock'
SMTP_USER=...
SMTP_PASS=...
SMTP_FROM_NAME=...
SMTP_FROM_EMAIL=...

# URLs
NEXT_PUBLIC_APP_URL=http://localhost:3000
```

---

## 🚀 Despliegue en Vercel
El proyecto está optimizado para despliegues CI/CD. Se han resuelto todas las validaciones de **ESLint** y **TypeScript** (`tsc --noEmit`) para garantizar builds estables en producción.

---
*Documentación generada para el reto GovTech Medellín - Hackathon 2026.*
