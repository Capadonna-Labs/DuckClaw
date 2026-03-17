# Optimización de la Interfaz Conversacional (UX/UI)

## 1. Objetivo Arquitectónico
Eliminar la redundancia informativa en las respuestas del agente (el "menú de opciones" automático) para transformar la interacción de un "bot de banco" a un "trabajador virtual" fluido. El agente debe adoptar un comportamiento **"Just-in-Time"**: solo ofrecer ayuda o menús cuando la intención del usuario sea ambigua o cuando el agente detecte un bloqueo en el flujo de trabajo.

## 2. Especificación de System Prompt (Refactorización)

El `system_prompt.md` de cada worker debe ser actualizado para eliminar la instrucción de listar capacidades al final de cada respuesta.

*   **Regla de Comportamiento:**
    > "NO listes tus capacidades, herramientas o menús de opciones al final de tus respuestas. Tu respuesta debe terminar en el dato solicitado o en una pregunta breve para resolver una ambigüedad. Si el usuario no sabe qué hacer, solo entonces ofrece ayuda brevemente."

*   **Regla de Concisión:**
    > "Si la respuesta es un dato (ej. saldo, hora, cotización), entrégalo de forma directa y limpia. No añadas rellenos como '¿Necesitas algo más?' a menos que sea estrictamente necesario para cerrar una transacción."

## 3. Especificación de Skill: `ResponseValidator` (Post-Processing)

Para garantizar que el agente cumpla con la concisión, el nodo `Explainer` (o el nodo final del grafo) debe aplicar un filtro de limpieza.

*   **Lógica:**
    1.  **Detección de Menú:** Si el LLM genera un bloque de texto que contiene "1. ... 2. ... 3. ..." o "Puedo ayudarte con:", el nodo debe truncar ese bloque antes de enviarlo al Gateway.
    2.  **Inyección de Contexto:** Si el agente detecta que el usuario está bloqueado (ej. el usuario responde "no entiendo"), el agente debe activar una bandera `show_help_menu: true` en el estado del grafo.
    3.  **Renderizado:** Solo si `show_help_menu` es `true`, el Gateway inyectará el menú de opciones en la respuesta final.

## 4. Contrato de API Gateway (Streaming Control)

El Gateway debe ser capaz de detectar si la respuesta del agente es "útil" o "ruido".

*   **Lógica:**
    ```python
    # services/api-gateway/main.py
    def clean_agent_response(response: str) -> str:
        # Regex para eliminar bloques de menús comunes
        cleaned = re.sub(r"¿Qué te gustaría hacer ahora\?.*", "", response, flags=re.DOTALL)
        cleaned = re.sub(r"- 📊 Resumen financiero.*", "", cleaned, flags=re.DOTALL)
        return cleaned.strip()
    ```

## 5. Roadmap de Implementación

1.  **Prompt Update:** Modificar `templates/workers/finanz/system_prompt.md` para eliminar la instrucción de listar capacidades.
2.  **Gateway Filter:** Implementar el `clean_agent_response` en el Gateway para filtrar menús residuales que el LLM pueda generar por inercia.
3.  **UX Testing:** Validar que el agente responda solo con el dato solicitado (ej. "Son las 11:52 AM") y no con el menú de opciones.