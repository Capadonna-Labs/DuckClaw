# Layer 2: Framework de Herramientas y Habilidades (Skills) 🛠️🚀

Define cómo los agentes interactúan con el entorno digital y ejecutan acciones complejas.

## 1. Ecosistema de Herramientas (Universal Skills)
- **Investigación Autónoma**: Integración de Tavily y Browser-Use para navegación web y extracción de datos en tiempo real.
- **Sandbox de Ejecución (Strix)**: Entorno Dockerizado y aislado para ejecutar código Python/Bash de forma segura.
- **GitHub MCP**: Integración con el ecosistema Model Context Protocol para interactuar con repositorios y flujos de desarrollo.

## 2. Interfaz Dinámica (On-the-Fly CLI)
El CLI `duckops` proporciona control administrativo agnóstico al sistema operativo:
- **Gestión de Servicios**: Status, Serve y Deploy.
- **Worker Factory**: Despliegue dinámico de plantillas de trabajadores virtuales.

## 3. Seguridad y Aislamiento
- **Vaulting**: Los secretos nunca tocan el disco en texto plano; se inyectan en tiempo de ejecución.
- **Auditoría de Acciones**: Cada ejecución de herramienta se registra con latencia y evidencia en DuckDB para auditoría posterior.
