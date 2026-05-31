# Criptografía y Seguridad: Funciones Hash (Hashing)

Una **Función Hash** es un algoritmo matemático que toma un conjunto de datos de cualquier longitud (la entrada) y lo transforma en una cadena de caracteres de longitud fija (la salida o *hash*). Esta salida actúa como la **huella digital** única de los datos originales.

---

## 1. Características Clave de una Función Hash

Para que un algoritmo de hash sea considerado seguro y útil en el desarrollo de software, debe cumplir con las siguientes propiedades:

*   **Determinística:** Si ingresas exactamente los mismos datos de entrada, el algoritmo siempre generará el mismo hash de salida.
*   **Eficiencia (Rápida):** El cálculo del hash debe ser computacionalmente rápido para cualquier tamaño de entrada.
*   **Unidireccional (Irreversible):** Es prácticamente imposible reconstruir los datos originales a partir de su hash de salida. No existe una función de "des-hashing".
*   **Resistente a Colisiones:** Debe ser extremadamente difícil (virtualmente imposible en algoritmos fuertes) encontrar dos entradas diferentes que produzcan el mismo hash de salida ($A \neq B$ pero $\text{Hash}(A) = \text{Hash}(B)$).
*   **Efecto Avalancha:** Un cambio minúsculo en los datos de entrada (como cambiar una sola letra de mayúscula a minúscula, o agregar un punto) produce un hash de salida completamente diferente e impredecible.

---

## 2. El Proceso de Hashing

El flujo general de procesamiento consta de las siguientes fases:

```text
  1. ENTRADA (Input)          2. PROCESAMIENTO             3. SALIDA ÚNICA (Hash)
┌────────────────────┐     ┌─────────────────────┐     ┌────────────────────────┐
│ - Texto plano      │     │                     │     │ Cadena de longitud     │
│ - Archivo (binario)├────►│   Algoritmo Hash    ├────►│ fija (ej. 256 bits).   │
│ - Imagen / Video   │     │ (SHA-256, BLAKE3...)│     │                        │
└────────────────────┘     └─────────────────────┘     └────────────────────────┘
```

### Ejemplo del Efecto Avalancha (SHA-256):

*   **Entrada:** `Hola Mundo`
    *   **Salida (Hash):** `a591a6d40bf420404a011733cfb7b190d62c651f5e7d4e331f0a9e6f94e6e0`
*   **Entrada:** `Hola mundo` (cambio de 'M' a 'm')
    *   **Salida (Hash):** `c53e8e9d9b6b8b1e3d3c4f0f9e8a7b17d2f5c6e8b9a0d1c2e3f4a5b6c7d8e9`
*   **Entrada:** `Hola Mundo!` (adición de '!')
    *   **Salida (Hash):** `f7b3c8a1d9e0f6b2a4c5d6e7f8a9b0c1e2d3c4b5a69787766554433221100`

---

## 3. Algoritmos de Hash Populares

Los algoritmos han evolucionado a medida que el poder de cómputo aumenta y se descubren vulnerabilidades:

| Algoritmo | Longitud de Salida | Estado de Seguridad | Notas de Uso |
| :--- | :--- | :--- | :--- |
| **MD5** | 128 bits | ❌ **Inseguro** | Vulnerable a colisiones. No usar en seguridad; solo para sumas de verificación rápidas no críticas. |
| **SHA-1** | 160 bits | ❌ **Obsoleto** | Teóricamente roto. Desaconsejado en la industria. |
| **SHA-256** | 256 bits |  **Seguro** | Parte de la familia SHA-2. Estándar de la industria y ampliamente utilizado. |
| **SHA-512** | 512 bits |  **Seguro** | Mayor resistencia que SHA-256, ideal para entornos de alta seguridad. |
| **BLAKE3** | Variable (256+ bits) |  **Seguro (Moderno)** | Extremadamente rápido, diseñado para paralelismo y criptográficamente seguro. |

---

## 4. Usos Principales en Ingeniería de Software

### A. Verificación de Integridad de Archivos
Permite confirmar que un archivo no ha sido alterado, corrompido o manipulado durante su almacenamiento o transmisión.

```text
[Emisor] Archivo original ──► Calcular SHA-256 ──► Envía Archivo + Hash firmado
                                                            │
                                                            ▼
[Receptor] Recibe Archivo ──► Calcula SHA-256 ──► ¿Coincide con el Hash firmado? ──► (Sí = Íntegro)
```

### B. Almacenamiento de Credenciales (Contraseñas)
Las contraseñas de los usuarios nunca se guardan en texto plano en la base de datos. Se guarda únicamente su representación en hash (idealmente enriquecida con un **Salt** para prevenir ataques de diccionario).

### C. Firmas Digitales y Certificados
En lugar de firmar un documento completo (que puede ser muy pesado), se calcula el hash del documento y se firma únicamente ese hash con una clave privada.

### D. Estructuras de Datos y Tecnología de Registro Distribuido (Blockchain)
*   **Tablas Hash (Hash Maps):** Utilizan funciones de hash rápidas para indexar elementos y lograr búsquedas en tiempo constante $O(1)$.
*   **Blockchain:** Cada bloque contiene el hash del bloque anterior, creando una cadena inmutable donde cualquier alteración en el pasado rompería la coherencia de todos los hashes posteriores.

---

## 5. Riesgos y Errores de Concepto Comunes

1.  **Confundir Hashing con Cifrado (Encryption):** 
    *   El **cifrado** es bidireccional: los datos se encriptan con una clave y se desencriptan con otra.
    *   El **hashing** es estrictamente unidireccional: no existe una "clave de descifrado" para volver al dato original.
2.  **Uso de algoritmos débiles para almacenamiento de contraseñas:** 
    *   Aunque SHA-256 es criptográficamente seguro, es un algoritmo diseñado para ser rápido (ideal para verificar gigabytes de archivos). Para contraseñas, se requiere un hash deliberadamente lento (como **Bcrypt** o **Argon2**) para mitigar ataques de fuerza bruta por hardware (GPUs).
3.  **No mitigar los ataques de colisión:**
    *   Si utilizas MD5 para verificar la autenticidad de firmas o archivos, un atacante sofisticado puede generar dos archivos diferentes con el mismo hash MD5, logrando suplantar un archivo legítimo por código malicioso.