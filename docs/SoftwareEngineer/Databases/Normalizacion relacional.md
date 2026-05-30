# Diseño de Bases de Datos: Normalización Relacional

La **normalización** es el proceso de estructurar y organizar los datos en un modelo relacional. Su propósito central es **reducir la redundancia de datos** y **eliminar anomalías** durante las operaciones de inserción, actualización y borrado (DML), garantizando así la integridad y consistencia de la información.

*   **Premisa fundamental:** *Menos redundancia se traduce en mayor consistencia.*

---

## 1. Objetivos del Proceso (¿Para qué sirve?)

*   **Evitar la duplicación de datos:** Reduce el consumo de almacenamiento innecesario.
*   **Garantizar la integridad referencial:** Protege las relaciones lógicas entre entidades.
*   **Simplificar el mantenimiento:** Las actualizaciones de datos se realizan en un único lugar, evitando inconsistencias (ej. cambiar el correo de un cliente una sola vez y no en cada pedido).
*   **Optimizar el rendimiento de escritura:** Al evitar tablas excesivamente anchas o redundantes, las operaciones de escritura/modificación se vuelven más ágiles.

---

## 2. Tipos de Dependencia de Datos

Para aplicar las reglas de normalización, primero se deben entender las relaciones de dependencia entre los atributos de una tabla:

*   **Dependencia Funcional ($A \rightarrow B$):** Ocurre cuando el valor de un atributo $A$ determina de manera única el valor de un atributo $B$.
*   **Dependencia Parcial:** En tablas con claves primarias compuestas (ej. `[id_pedido, id_producto]`), ocurre si un atributo no clave depende únicamente de una *parte* de la clave primaria en lugar de la clave completa.
*   **Dependencia Transitiva ($A \rightarrow B \rightarrow C$):** Ocurre cuando un atributo no clave $C$ depende de otro atributo no clave $B$, el cual a su vez depende de la clave primaria $A$.

---

## 3. El Proceso de Normalización en 4 Pasos

El modelado sigue un flujo incremental para transformar un esquema plano en un esquema relacional maduro:

```text
  1. Identificar atributos ────► 2. Eliminar grupos ────► 3. Dividir tablas ────► 4. Relacionar tablas
    y dependencias                 repetidos y duplicados      según reglas (FN)          pequeñas y coherentes
```

---

## 4. Las Formas Normales (FN)

Las formas normales son un conjunto de reglas aplicadas de forma progresiva. Cada nivel requiere que se cumplan las reglas del nivel anterior.

### Primera Forma Normal (1FN): Atomicidad
*   **Regla:** Todos los atributos deben ser atómicos (valores indivisibles). No se permiten grupos repetidos, listas, ni arreglos dentro de una celda.
*   **Acción:** Separar valores múltiples en registros independientes o tablas secundarias.

### Segunda Forma Normal (2FN): Dependencia Completa
*   **Regla:** Debe cumplir con la 1FN y **no deben existir dependencias parciales**. Todos los atributos no clave deben depender por completo de la clave primaria (completa).
*   **Acción:** Si un atributo solo depende de una parte de una clave primaria compuesta, se debe extraer a una tabla nueva con su clave correspondiente.

### Tercera Forma Normal (3FN): No Transitividad
*   **Regla:** Debe cumplir con la 2FN y **no deben existir dependencias transitivas**. Los atributos que no son clave no deben depender de otros atributos que tampoco son clave.
*   **Acción:** Separar el subgrupo de dependencias en una tabla independiente con su propia clave.

### Forma Normal de Boyce-Codd (BCNF)
*   **Regla:** Versión estrictamente definida de la 3FN. Requiere que para cualquier dependencia funcional $A \rightarrow B$, $A$ deba ser una clave candidata (superclave).

---

## 5. Caso de Estudio: Antes vs. Después

### Escenario Sin Normalizar (Esquema Plano)

La siguiente tabla de `Pedidos` presenta redundancia severa en los datos del cliente y mezcla responsabilidades físicas y comerciales:

| id_pedido | cliente | producto | cliente_email | precio |
| :--- | :--- | :--- | :--- | :--- |
| **1** | Ana | Laptop | `ana@mail.com` | 1200 |
| **2** | Ana | Mouse | `ana@mail.com` | 20 |
| **3** | Luis | Teclado | `luis@mail.com` | 30 |
| **4** | Luis | Monitor | `luis@mail.com` | 150 |

*   ❌ **Problemas detectados:**
    *   **Datos Duplicados:** El nombre y el correo de "Ana" y "Luis" se repiten en cada transacción.
    *   **Anomalía de Actualización:** Si "Ana" cambia de correo, se deben modificar múltiples filas con riesgo de inconsistencia si alguna falla.
    *   **Anomalía de Eliminación:** Si eliminamos el único pedido de un cliente, perdemos toda su información de contacto.

---

### Escenario Normalizado (Esquema Relacional)

Aplicando las Formas Normales, dividimos la responsabilidad única en cuatro tablas conectadas mediante claves foráneas (FK):

```text
    ┌──────────────────┐               ┌─────────────────┐
    │     Clientes     │               │     Pedidos     │
    ├──────────────────┤               ├─────────────────┤
    │ id_cliente (PK)  │◄─────────────┐│ id_pedido (PK)  │◄────────────┐
    │ nombre           │               │ id_cliente (FK) │             │
    │ email            │               │ fecha           │             │
    └──────────────────┘               └─────────────────┘             │
                                                                       │
    ┌──────────────────┐               ┌─────────────────┐             │
    │    Productos     │               │ Detalles_Pedido │             │
    ├──────────────────┤               ├─────────────────┤             │
    │ id_producto (PK) │◄─────────────┐│ id_pedido (FK)  ├─────────────┘
    │ nombre           │              ││ id_producto (FK)│
    │ precio_lista     │              ││ precio_venta    │
    └──────────────────┘              └└─────────────────┘
```

#### Atributos de las tablas resultantes:

*   **`Clientes`** `(id_cliente [PK], nombre, email)`
*   **`Productos`** `(id_producto [PK], nombre, precio_lista)`
*   **`Pedidos`** `(id_pedido [PK], id_cliente [FK], fecha)`
*   **`Detalles_Pedido`** `(id_pedido [FK], id_producto [FK], precio_venta)` *(Nota: Almacenar `precio_venta` aquí evita perder el histórico comercial si el precio de lista del producto cambia en el futuro).*

*   ── **Beneficios obtenidos:**
    *   Cero duplicación de información de contacto o de catálogos.
    *   Integridad referencial protegida.
    *   Las consultas de lectura pesadas se resuelven de forma eficiente a través de operaciones `JOIN`.

---

## 6. Errores Comunes en el Modelado

1.  **Omitir Claves Primarias (PK):** Diseñar tablas sin un identificador único que garantice la identidad de cada tupla.
2.  **Mantener Atributos Redundantes:** Almacenar la misma información mutable en diferentes partes del sistema.
3.  **Ignorar Dependencias Transitivas:** Permitir que campos descriptivos dependan indirectamente de la clave principal a través de un intermediario (ej. colocar la dirección de la tienda dentro de la tabla de inventario del producto).
4.  **No aplicar el principio de responsabilidad única (SRP):** Diseñar tablas gigantescas con propósitos mixtos en lugar de separar entidades lógicas claramente delimitadas.

---

## 7. Regla de Oro

> **"Normaliza hasta la Tercera Forma Normal (3FN) en la gran mayoría de tus casos prácticos de negocio. Utiliza BCNF o formas superiores únicamente cuando la integridad y el rigor de los datos sean críticos para el dominio."**

*   *Nota de Arquitectura:* En sistemas modernos con alta carga de lectura (como almacenes de datos, analítica o sistemas NoSQL), en ocasiones se recurre de forma intencionada a la **Desnormalización** para optimizar el rendimiento de lectura sacrificando espacio de almacenamiento. Sin embargo, este paso siempre debe darse *después* de haber comprendido y diseñado el esquema normalizado correspondiente.