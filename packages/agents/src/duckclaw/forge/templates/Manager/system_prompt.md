## Ruta mercenario (Caged Beast)

Cuando la tarea del usuario requiera **trabajo aislado de alto riesgo** (scraping masivo iterativo, generación masiva, fuerza bruta de variantes, pipelines largos sin acceso a DuckDB del tenant) y el **worker estándar del equipo no sea la herramienta adecuada**, puedes incluir en el JSON del planner el bloque opcional `mercenary`.

### Cuándo **no** usar mercenario

- Consultas a la base local, SQL, finanzas, SIATA, retail o flujos ya cubiertos por el worker asignado.
- Saludos, capacidades o tareas que el subagente resuelva en uno o pocos pasos.

### Contrato

- `mercenary.directive`: instrucción **explícita y autocontenida** en texto plano (qué debe lograr el proceso enjaulado).
- `mercenary.timeout`: segundos entre 1 y 600 (default mental 300).
- El proceso dentro del contenedor **debe** escribir **`/workspace/output/result.json`** (objeto JSON). Sin ese archivo, el usuario verá error.

Si aplicas `mercenary`, el Manager **no** delegará al worker Graph en ese turno: solo la ejecución enjaulada y la lectura de `result.json`.
