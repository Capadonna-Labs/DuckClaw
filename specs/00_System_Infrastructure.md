# Layer 0: Infraestructura y Orquestación del Sistema 🏗️

Esta especificación consolida la conectividad, seguridad y despliegue del ecosistema DuckClaw.

## 1. Conectividad: Tailscale Mesh
DuckClaw utiliza **Tailscale (WireGuard)** para crear una red privada cifrada de punto a punto (E2EE) entre nodos (Mac Mini local y VPS remoto).
- **Seguridad**: Zero-Trust mediante ACLs de Tailscale.
- **Autenticación**: Validación de `X-Tailscale-Auth-Key` en todos los endpoints de invocación.

## 2. API Gateway (FastAPI)
El Gateway es el único punto de entrada para servicios externos (Angular, n8n).
- **Módulos**: Agent Chat (SSE Streaming), Homeostasis Status y System Health.
- **Middleware**: Gestiona el Rate Limiting (`slowapi`) y el enmascaramiento de datos sensibles (Habeas Data).

## 3. Despliegue y Persistencia (PM2 / Docker)
- **Modo Local/Híbrido**: PM2 gestiona los procesos `DuckClaw-Brain` (Bot) y `DuckClaw-Inference` (MLX).
- **Contenerización**: Docker multi-etapa para aislamiento de procesos y escalamiento elástico en Kubernetes.

## 4. CI/CD Distribuido
Pipeline unificado para construir el núcleo C++ y desplegar agentes en caliente (Hot-Swap) una vez superadas las pruebas de validación semántica.
