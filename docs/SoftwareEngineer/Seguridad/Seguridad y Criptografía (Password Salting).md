
El **Salt** (sal) es un valor aleatorio y único que se genera para cada usuario y se combina con su contraseña antes de procesarla con una función hash. Su principal propósito es garantizar que contraseñas idénticas produzcan *hashes* completamente diferentes, protegiendo la base de datos contra ataques de diccionario precomputados (como las tablas arcoíris).

---

## 1. La Fórmula del Hash con Salt

En un sistema seguro, el proceso de hashing no se aplica sobre la contraseña en texto plano de manera directa, sino sobre la combinación de esta con el valor aleatorio:

$$\text{HASH} = \text{Función\_Hash}(\text{Contraseña} + \text{Salt})$$

*   **Nota de diseño:** El *salt* no es secreto. Se almacena junto con el *hash* en la base de datos, ya que el sistema lo necesita para verificar la contraseña en futuros inicios de sesión.

---

## 2. Comparativa: ¿Por qué es inseguro no usar Salt?

### Escenario A: Sin Salt (Inseguro)
Si dos usuarios eligen la misma contraseña, el sistema generará exactamente el mismo hash.

| Usuario | Contraseña | Proceso de Hash | Hash Resultante (MD5 ej.) |
| :--- | :--- | :--- | :--- |
| **Usuario A** | `123456` | $\text{Hash}(123456)$ | `e10adc3949ba59abbe56e057f20f883e` |
| **Usuario B** | `123456` | $\text{Hash}(123456)$ | `e10adc3949ba59abbe56e057f20f883e` |

*   ❌ **Vulnerabilidad:** Si un atacante roba la base de datos, puede usar una **Tabla Arcoíris (Rainbow Table)** —una base de datos precomputada con millones de contraseñas comunes y sus respectivos hashes— para revertir instantáneamente la contraseña de todos los usuarios que compartan ese valor.

### Escenario B: Con Salt (Seguro)
Incluso si dos usuarios eligen la misma contraseña, sus hashes finales serán únicos debido al salt individual.

| Usuario | Contraseña | Salt generado (Aleatorio) | Proceso de Hash | Hash Resultante |
| :--- | :--- | :--- | :--- | :--- |
| **Usuario A** | `123456` | `a1b2c3d4e5f6g7h8` | $\text{Hash}(123456 + \text{a1b2...})$ | `5f4dcc3b5aa765d...` |
| **Usuario B** | `123456` | `z9y8x7w6v5u4t3s2` | $\text{Hash}(123456 + \text{z9y8...})$ | `d3b07384d113ede...` |

*   ── **Protección:** Las tablas arcoíris precomputadas quedan completamente inutilizadas, ya que el atacante tendría que calcular una tabla nueva adaptada para cada *salt* individual de cada usuario, volviendo el ataque computacionalmente inviable.

---

## 3. Flujo de Funcionamiento del Patrón

El flujo se divide en dos fases: el registro (creación) y la verificación (autenticación).

```text
[REGISTRO]
Usuario crea cuenta ──► Generar Salt Aleatorio ──► Concatenar (Pass + Salt) ──► Aplicar Hash Fuerte ──► Guardar en BD (Salt + Hash)

[VERIFICACIÓN]
Usuario inicia sesión ──► Recuperar Salt de la BD ──► Concatenar (Input + Salt) ──► Aplicar Hash Fuerte ──► ¿Coincide con Hash en BD?
```

---

## 4. Variaciones y Conceptos Relacionados

### 1. Salt Aleatorio (Recomendado)
Un valor criptográficamente seguro y único generado de manera dinámica en el momento de la creación de la cuenta. 

### 2. Salt Único por ID (No recomendado)
Utilizar una propiedad estática del usuario (como su `ID` de base de datos o su `username`) como salt. Aunque proporciona unicidad, no es óptimo porque reduce el espacio de aleatoriedad disponible si el atacante conoce la estructura de dichos identificadores.

### 3. Pepper (Pimienta - Opcional)
Un **Pepper** es un valor secreto global que se añade a la contraseña además del *salt*. 
*   **Diferencia clave:** A diferencia del salt, el pepper **no** se almacena en la base de datos de usuarios; se guarda en un lugar seguro fuera de ella (ej. variables de entorno del servidor o un módulo de seguridad de hardware / HSM). Si la base de datos es comprometida pero el servidor no, el atacante sigue sin poder iniciar un ataque de fuerza bruta eficiente.

---

## 5. Mejores Prácticas de Implementación

1.  **Utilizar algoritmos de hashing lentos (adaptables):** Evita funciones rápidas como MD5, SHA-1 o SHA-256 para almacenar contraseñas. Utiliza algoritmos diseñados específicamente para hashing de contraseñas que incluyan un factor de trabajo o costo configurable:
    *   **Bcrypt:** (Establece rondas de costo, recomendado 10-12 en servidores modernos).
    *   **Argon2:** (Ganador de la Password Hashing Competition; altamente resistente a ataques por GPU/ASIC).
    *   **Scrypt** y **PBKDF2**.
    
    *(Nota: Muchos de estos algoritmos modernos integran y gestionan de forma automática la generación y codificación del salt dentro de la misma cadena hash resultante, por ejemplo: `$2b$10$wJH8Q7h...`).*

2.  **Tamaño del Salt:** Debe tener una longitud mínima de **16 bytes** generados por un generador de números pseudoaleatorios criptográficamente seguro (CSPRNG).
3.  **No reutilizar salts:** Nunca utilices el mismo salt para más de un usuario.
4.  **Proteger el tránsito:** El salt protege la contraseña en reposo (en la base de datos). Para protegerla en tránsito, es obligatorio utilizar protocolos seguros como **HTTPS/TLS**.