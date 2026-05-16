No pude completar la inferencia: el motor local (p. ej. MLX) no respondió o se reinició, a veces por **falta de memoria GPU**. Revisa `pm2 logs MLX-Inference`.

Si el fallo fue tras `/context --summary`, prueba bajar el volcado con la variable `DUCKCLAW_SEMANTIC_SUMMARY_MAX_CHARS` (p. ej. 6000) o desactiva la segunda pasada de síntesis con `DUCKCLAW_DISABLE_NL_REPLY_SYNTHESIS=1`.
