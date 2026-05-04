Objetivo

Definir un formato mínimo obligatorio para que cualquier plan sea:





robusto técnicamente,



entendible para perfiles no técnicos,



ejecutable por desarrollo sin ambigüedad.

Estructura obligatoria de todo plan





Nombre del plan





Debe describir la solución objetivo, no “notas” o “correcciones”.



Problema y objetivo funcional





Qué problema resuelve.



Qué cambia para el usuario.



Qué no está incluido (out of scope).



Definiciones funcionales





Definir términos clave (ej. “etiqueta”, “global”, “personal”).



Incluir propósito de cada entidad funcional.



Reglas de negocio





Reglas obligatorias.



Reglas de validación.



Reglas de visibilidad/permisos.



Reglas anti-duplicidad y manejo de errores.



Módulos y vistas impactadas





Qué módulo cambia.



Qué vista específica cambia.



Qué acción se podrá hacer allí (ver, crear, editar, eliminar, filtrar).



Modelo de datos





Tablas nuevas y tablas modificadas.



Objetivo de cada tabla.



Objetivo de relaciones y constraints.



Endpoints API





Lista de endpoints.



Qué recibe cada uno.



Qué retorna cada uno.



Casos de error esperados (mínimo).



Flujo operativo paso a paso





Secuencia legible por negocio (no solo diagrama técnico).



Debe responder: quién hace qué, dónde, y qué pasa después.



Trazabilidad / auditoría





Qué eventos se registran.



Dónde se registran.



Qué metadata mínima se guarda.



UI/UX





Patrón elegido (y por qué).





Comportamiento en escritorio/móvil.



Estados de carga, vacío, error y éxito.



Archivos a crear y archivos a modificar





Separar claramente ambos listados.





Explicar para qué se toca cada archivo.



Integración técnica





Vite/assets.





Rutas.



Servicios/controladores.



Dependencias si aplica.



Pruebas y criterios de aceptación





Casos funcionales mínimos.





Casos de permisos.



Casos de duplicidad y concurrencia.



Criterios de “Done”.

Checklist de calidad (obligatorio antes de aprobar)





El plan explica el problema en lenguaje no técnico.



Están definidos los conceptos clave y su propósito.



Hay reglas claras de visibilidad/permisos.



Se especifica en qué vistas se ve y en cuáles se edita.



Se detallan endpoints con request/response.



El flujo paso a paso lo entiende negocio.



Se define trazabilidad funcional y administrativa.



Lista completa de archivos a crear/modificar.



Incluye integración de assets en Vite/renders.



Incluye pruebas y criterios de aceptación medibles.

Criterio de rechazo automático del plan

Un plan se considera incompleto si:





no indica dónde se visualiza y dónde se edita,



no define contratos API,



no incluye trazabilidad,



o no detalla archivos impactados.

