No pude completar la inferencia con **Groq**: el envío supera el límite de tokens de tu plan (p. ej. ~12k TPM en tier on_demand). El gateway ya omite herramientas **reddit_*** en rutas genéricas con Groq para ahorrar esquema; si sigue fallando, prueba:
- `DUCKCLAW_GROQ_MAX_INPUT_TOKENS` más bajo y/o `DUCKCLAW_GROQ_TOOL_MESSAGE_MAX_CHARS` más bajo
- Acortar el historial del chat o subir tier en console.groq.com
- `DUCKCLAW_DISABLE_NL_REPLY_SYNTHESIS=1` si ocurre tras muchas herramientas.
