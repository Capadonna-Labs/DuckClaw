# Layer 1: Memoria Analítica y Arquitectura de Datos 🧠💾

Consolidación de las capacidades de persistencia, búsqueda semántica y transferencia de datos de alto rendimiento.

## 1. Motores de Persistencia Híbrida
- **DuckDB (Analítico/OLAP)**: Motor principal para grandes volúmenes de datos financieros y operativos.
- **Redis (Estado/Locks)**: Gestión de colas de escritura y coordinación de sesiones efímeras.

## 2. Memoria Estructural (PGQ + Vector RAG)
DuckClaw combina dos formas de recuperación de memoria en un solo motor (DuckDB):
- **GraphRAG (DuckDB PGQ)**: Relaciones complejas `(Entidad)-[:REL]->(Entidad)` para razonamiento multi-salto.
- **Vector Search (DuckDB VSS)**: Búsqueda por similitud de coseno sobre embeddings locales (Cero dependencias de nube).

## 3. Pipeline Zero-Copy (Apache Arrow)
Para maximizar el rendimiento, DuckClaw utiliza el formato **Apache Arrow** para mover datos entre el núcleo C++ y los servicios Python/Docker sin serialización JSON redundante.
- **ArrowBridge**: Intercambio de memoria compartida.
- **Sandbox Integration**: Los datos se inyectan en el Sandbox como archivos Parquet optimizados.

## 4. Estrategia de Persistencia (Habeas Data)
- **Singleton Writer Bridge**: Todas las escrituras pasan por una cola única para evitar bloqueos competitivos en DuckDB.
- **Derecho al Olvido**: Borrado granular de nodos en el grafo de conocimiento sin afectar la integridad del sistema.
