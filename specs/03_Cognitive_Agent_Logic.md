# Layer 3: Lógica Cognitiva y Agentes Inteligentes 🤖🧠

Consolidación de la arquitectura de razonamiento, gestión de ciclo de vida y homeostasis de los agentes.

## 1. Arquitectura de Agentes Homeostáticos
Basada en el **Active Inference Framework**, los agentes no solo reaccionan, sino que monitorean su propia salud y precisión semántica.
- **Beliefs (Creencias)**: Predicciones del modelo que se ajustan con la evidencia de las herramientas.
- **Corrección de Deriva**: Shadow Inference para detectar alucinaciones comparando modelos nuevos vs anteriores.

## 2. Gestión de Ciclo de Vida (Worker Factory)
Sistema de plantillas para instanciar trabajadores especializados con roles predefinidos (Finanz, Support, Researcher).
- **Handoff (HITL)**: Protocolo de escalamiento a humano cuando la incertidumbre supera el umbral permitido o se requiere aprobación financiera.

## 3. Gestión de Contexto (Memory Windowing)
Optimización del uso de tokens mediante ventanas de memoria dinámicas:
- **Resumen Progresivo**: Los diálogos antiguos se destilan en "recuerdos" en el grafo de conocimiento antes de salir del buffer de tokens.
- **Context Management**: Selección selectiva de información basada en la relevancia de la tarea actual.

## 4. Validación y Model-Guard
Pipeline de evaluación continua que valida las respuestas del agente contra un "Golden Dataset" antes de permitir el despliegue de nuevas versiones del grafo.
