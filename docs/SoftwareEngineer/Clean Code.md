# SPEC — Clean Code

> Versión: 1.0.0 | Tipo: Estándar de Desarrollo Transversal  
> Aplica a: Cualquier lenguaje, equipo y tipo de proyecto de software

---

## Definición

**Clean Code** (código limpio) es código que cualquier desarrollador puede leer, entender, modificar y extender con mínimo esfuerzo cognitivo, sin necesidad del autor original ni comentarios explicativos excesivos.

```
Código sucio:  Funciona hoy. Nadie sabe cómo ni por qué. Modificarlo da miedo.
Código limpio: Funciona hoy. Cualquiera entiende qué hace y por qué. Modificarlo es seguro.
```

> **Regla de oro**: El código se lee muchas más veces de las que se escribe.  
> Escribir código es para humanos, no para máquinas. La máquina ejecuta cualquier cosa.

---

## Los 6 Principios Clave

### 1. Legibilidad

El código debe leerse como texto en prosa. Si necesitas un comentario para explicar _qué_ hace una línea, el código no es suficientemente claro.

```
PREGUNTA: ¿Puedo entender qué hace este bloque en 10 segundos sin comentarios?
Si la respuesta es NO → refactorizar.
```

### 2. Simplicidad

Hacer lo mínimo necesario para resolver el problema. Evitar abstracciones prematuras, complejidad innecesaria y código que "podría servir en el futuro".

```
YAGNI (You Aren't Gonna Need It):
  No implementar funcionalidad hasta que sea realmente necesaria.
  El código que no existe no tiene bugs ni necesita mantenimiento.

KISS (Keep It Simple, Stupid):
  La solución más simple que funciona correctamente es la correcta.
  La complejidad solo se justifica si el problema es complejo.
```

### 3. Nombres que revelan intención

El nombre de una variable, función, clase o módulo debe responder:  
**¿Por qué existe? ¿Qué hace? ¿Cómo se usa?**

```
VARIABLES:

  ❌ d        ✅ dias_hasta_vencimiento
  ❌ temp     ✅ temperatura_actual_celsius
  ❌ proc     ✅ procesar_pago
  ❌ list     ✅ lista_productos_activos
  ❌ val      ✅ es_usuario_valido
  ❌ data     ✅ datos_pedido
  ❌ x, y     ✅ latitud, longitud
  ❌ i        ✅ indice_pagina (si el contexto no es obvio)

FUNCIONES:
  El nombre debe describir QUÉ hace, no CÓMO lo hace.
  Deben ser verbos o frases verbales.

  ❌ f(d)              ✅ calcular_total_ventas(ventas)
  ❌ procesar(item)    ✅ aplicar_descuento(producto)
  ❌ check(u)          ✅ verificar_credenciales_usuario(usuario)
  ❌ getData()         ✅ obtener_perfil_usuario(id_usuario)

BOOLEANOS:
  Deben leerse como preguntas de sí/no.

  ❌ activo      ✅ esta_activo
  ❌ habilitado  ✅ tiene_permiso_escritura
  ❌ verificado  ✅ es_email_verificado

CLASES:
  Sustantivos que representan una entidad o concepto.

  ❌ Manager, Helper, Utility, Processor (demasiado genéricos)
  ✅ GestorPedidos, CalculadorImpuestos, ValidadorEmail
```

### 4. Funciones Pequeñas con Una Sola Responsabilidad

Una función debe hacer **una sola cosa**, hacerla **bien** y hacerla **solo**.

```
REGLA DEL TAMAÑO:
  Líneas ideales por función: 5–15
  Límite razonable: ~20 líneas
  Si supera 30 líneas: probablemente está haciendo demasiado → dividir

SEÑALES DE QUE UNA FUNCIÓN HACE DEMASIADO:
  - Tiene "and" u "or" en su nombre: guardar_y_enviar_email()
  - Requiere scroll para verla completa
  - Tiene múltiples niveles de indentación (> 2 niveles)
  - Necesita muchos comentarios para entenderse

TRANSFORMACIÓN:
  ANTES (función que hace demasiado):
    calcular_pedido(items, usuario, descuento, envio):
      total = 0
      for item in items:
        if item["cantidad"] > 0 and item["precio"] < 1000:
          total += item["cantidad"] * item["precio"] * 2
      if descuento:
        total = total - (total * descuento)
      envio_costo = calcular_envio(usuario["ciudad"])
      total = total + envio_costo
      return total

  DESPUÉS (funciones con responsabilidad única):
    calcular_total_pedido(items, descuento, costo_envio):
      subtotal = calcular_subtotal(items)
      subtotal_con_descuento = aplicar_descuento(subtotal, descuento)
      return subtotal_con_descuento + costo_envio

    calcular_subtotal(items):
      return sum(calcular_importe(item) for item in items if es_valido(item))

    es_valido(item):
      return item.cantidad > 0 and item.precio < 1000

    calcular_importe(item):
      return item.cantidad * item.precio * FACTOR_MULTIPLICADOR

    aplicar_descuento(total, porcentaje_descuento):
      return total * (1 - porcentaje_descuento)
```

### 5. No Repetir Código (DRY — Don't Repeat Yourself)

```
PRINCIPIO DRY:
  Cada pieza de conocimiento o lógica debe tener una representación
  ÚNICA, AUTORITATIVA y DESAMBIGUA en el sistema.

SEÑALES DE VIOLACIÓN DRY:
  - Copiar y pegar bloques de código entre funciones o clases
  - La misma validación aparece en 5 lugares distintos
  - Al cambiar una regla de negocio hay que buscarla en múltiples archivos

CONSECUENCIA DE WET CODE (Write Everything Twice):
  Un bug se corrige en un lugar → sigue existiendo en los otros 4
  Una regla cambia → hay que actualizar todos los duplicados → fácil olvidar uno

SOLUCIONES:
  Extraer en función reutilizable
  Extraer en clase base o mixin
  Extraer en módulo compartido
  Usar constantes para valores mágicos repetidos
```

### 6. Código Fácil de Mantener y Extender

```
DISEÑO PARA EL CAMBIO:
  El código cambia. La pregunta no es si cambiará, sino cuándo.
  
  ANTES de agregar una feature: ¿puedo hacerlo sin modificar código existente?
  → Ideal: solo agregar código nuevo (Open/Closed Principle)
  → Si hay que modificar mucho código existente: la estructura necesita refactoring

INDICADORES DE CÓDIGO MANTENIBLE:
  ✓ Tests automatizados que validan el comportamiento
  ✓ Dependencias explícitas (inyección de dependencias)
  ✓ Módulos con acoplamiento bajo y cohesión alta
  ✓ Interfaces claras entre módulos
  ✓ Configuración externalizada (no valores en el código)
```

---

## Valores Mágicos — Prohibidos

Los **números mágicos** y **strings mágicos** son literales que aparecen en el código sin nombre ni explicación.

```
❌ CÓDIGO CON VALORES MÁGICOS:
  if usuario.edad >= 18:
      precio = precio * 0.15
      if reintentos > 3:
          esperar(30)

✅ CÓDIGO CON CONSTANTES NOMBRADAS:
  EDAD_MAYORIA = 18
  TASA_DESCUENTO_ADULTO = 0.15
  MAX_REINTENTOS = 3
  TIEMPO_ESPERA_REINTENTO_SEGUNDOS = 30

  if usuario.edad >= EDAD_MAYORIA:
      precio = precio * TASA_DESCUENTO_ADULTO
      if reintentos > MAX_REINTENTOS:
          esperar(TIEMPO_ESPERA_REINTENTO_SEGUNDOS)

BENEFICIO: Si la tasa cambia de 15% a 20%, se cambia en UN solo lugar.
           Si el tiempo de espera cambia, es obvio qué significa.
```

---

## Comentarios — Cuándo Sí y Cuándo No

```
COMENTARIOS BUENOS (explican el POR QUÉ, no el QUÉ):

  # Usamos Levenshtein en lugar de igualdad exacta porque los nombres
  # de proveedores tienen errores tipográficos frecuentes (dato histórico)
  distancia = levenshtein(nombre_proveedor, nombre_registrado)

  # RFC 7519 requiere que exp sea Unix timestamp, no ISO 8601
  expiracion = int(tiempo_actual.timestamp()) + DURACION_TOKEN

  # WORKAROUND: La API de pagos retorna 200 incluso en fallos.
  # Verificar el campo "status" en el body. Issue #1234.
  if respuesta.status_code == 200 and respuesta.json()["status"] == "error":

COMENTARIOS MALOS (explican el QUÉ, que ya es obvio en el código):

  # Incrementar contador en 1
  contador += 1

  # Verificar si el usuario está activo
  if usuario.esta_activo:

  # Loop sobre la lista de usuarios
  for usuario in usuarios:

REGLA: Si el comentario dice lo mismo que el código, el comentario sobra.
       Si necesitas comentar el QUÉ → el código no es suficientemente claro → refactorizar.
```

---

## Formato y Consistencia

El formato del código debe ser **uniforme en todo el proyecto**. No importa cuál convención se elija; importa que sea la misma en todos lados.

```
ELEMENTOS A ESTANDARIZAR:
  - Indentación: espacios vs tabs, cantidad (2 o 4 espacios — nunca mezclar)
  - Longitud máxima de línea: 80–120 caracteres
  - Convención de nombres: camelCase, snake_case, PascalCase (por tipo de elemento)
  - Orden de imports/dependencias
  - Líneas en blanco entre secciones
  - Llaves y bloques de control

HERRAMIENTAS DE FORMATO AUTOMÁTICO:
  No debatir el formato — automatizarlo con linters y formatters:
  - Ejecutar en pre-commit hook
  - Ejecutar en CI pipeline
  - Si falla el formato → el CI falla → no se mergea el código

PRINCIPIO: El estilo del código no debe revelar quién lo escribió.
           Todo el código debe parecer escrito por la misma persona.
```

---

## Eliminación de Código Muerto

```
CÓDIGO MUERTO: código que existe en el repositorio pero nunca se ejecuta.
  - Funciones definidas pero nunca llamadas
  - Variables declaradas pero nunca usadas
  - Bloques comentados que "podrían servir"
  - Imports no utilizados
  - Features flags siempre en false
  - Ramas de condicional imposibles

POR QUÉ ELIMINARLO:
  ✗ Confunde a quien lee el código ("¿esto se usa? ¿debo considerarlo?")
  ✗ Ocupa espacio en el repositorio
  ✗ Los linters lo reportan como advertencia
  ✗ Puede ejecutarse accidentalmente al refactorizar

SOLUCIÓN:
  El código muerto va al historial de git, no al archivo.
  Si algún día se necesita: git log, git blame, git checkout.
  NO: comentar código "por si acaso".
  SÍ: eliminar y confiar en el control de versiones.
```

---

## Refactoring — Cómo Mejorar Código Existente

```
DEFINICIÓN:
  Refactoring = cambiar la estructura interna del código
  SIN cambiar su comportamiento externo observable.

CUÁNDO REFACTORIZAR:
  - Antes de agregar una nueva feature (preparar el terreno)
  - Al encontrar código que no se entiende al leerlo
  - Cuando los tests fallan y el código es difícil de modificar
  - Al detectar duplicación (DRY violation)
  - Regla del Boy Scout: deja el código un poco mejor de como lo encontraste

PROCESO SEGURO DE REFACTORING:
  1. Tener tests que validen el comportamiento actual
  2. Hacer un cambio pequeño
  3. Ejecutar los tests → deben seguir pasando
  4. Repetir

SIN TESTS → NO REFACTORIZAR (riesgo de romper comportamiento sin saberlo)
```

---

## Code Smells — Señales de Alerta

|Smell|Descripción|Solución|
|---|---|---|
|**Long Method**|Función demasiado larga|Extraer en subfunciones|
|**Large Class**|Clase con demasiadas responsabilidades|Dividir en clases especializadas|
|**Duplicate Code**|Lógica repetida en múltiples lugares|Extraer a función/módulo reutilizable|
|**Long Parameter List**|Función con muchos parámetros (>3-4)|Encapsular en objeto/struct|
|**Feature Envy**|Una función usa datos de otra clase más que los propios|Mover la función a donde pertenece|
|**Magic Numbers**|Literales sin nombre ni explicación|Extraer a constantes nombradas|
|**Dead Code**|Código no ejecutado|Eliminar|
|**Comments for What**|Comentarios que explican código obvio|Mejorar el código hasta que sea auto-explicativo|
|**Deeply Nested Code**|Más de 2-3 niveles de indentación|Cláusulas de guarda, extracción de funciones|
|**God Class**|Una clase que lo sabe y hace todo|Distribuir responsabilidades|
|**Shotgun Surgery**|Un cambio requiere modificar muchos archivos|Consolidar responsabilidad|

---

## Checklist de Clean Code por Entidad

### Variables

- [ ] El nombre revela propósito sin contexto adicional
- [ ] No usa abreviaciones (excepto convenciones universales: `id`, `url`, `html`)
- [ ] Los booleanos se leen como pregunta: `es_`, `tiene_`, `puede_`, `esta_`
- [ ] No existen variables globales mutables innecesarias

### Funciones

- [ ] El nombre describe qué hace (verbo + sustantivo)
- [ ] Hace una sola cosa
- [ ] Tiene menos de ~20 líneas
- [ ] Tiene menos de 4 parámetros (si tiene más: revisar responsabilidad)
- [ ] No tiene efectos secundarios ocultos
- [ ] No usa valores mágicos — usa constantes nombradas

### Módulos / Clases

- [ ] Tiene una única responsabilidad clara
- [ ] Nombre en sustantivo que representa la entidad
- [ ] Dependencias explícitas (inyectadas, no instanciadas internamente)
- [ ] No tiene código muerto ni funciones nunca llamadas

### Proyecto

- [ ] Linter y formatter configurados y ejecutados en CI
- [ ] Convenciones documentadas en CONTRIBUTING.md o similar
- [ ] Tests que validan el comportamiento (permiten refactorizar con seguridad)
- [ ] Sin código comentado en el repositorio

---

> **CÓDIGO LIMPIO = Legible + Simple + Mantenible + Escalable + Profesional**  
> "El tiempo que tardas en entender código mal escrito es tiempo que no estás creando valor."