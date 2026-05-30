# SPEC — Cookies

> Versión: 1.0.0 | Tipo: Protocolo HTTP / Estado de Sesión | Aplica a: Cualquier stack web

---

## Definición

Una **cookie** es un pequeño fragmento de datos (clave=valor) que el servidor envía al navegador del cliente, el cual lo almacena y lo reenvía automáticamente en cada petición HTTP posterior al mismo dominio.

```
Sin cookies: El servidor no puede distinguir entre peticiones del mismo usuario.
Con cookies: El servidor puede mantener estado entre peticiones (sesiones, preferencias, auth).
```

**Naturaleza**: Las cookies son parte del protocolo HTTP. El servidor las establece mediante el header `Set-Cookie`; el navegador las retorna mediante el header `Cookie`.

---

## Ciclo de Vida

```
1. SOLICITUD INICIAL
   Cliente  →  GET /login  →  Servidor

2. ESTABLECIMIENTO
   Servidor → Set-Cookie: session_id=abc123; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=3600
            → 200 OK + contenido

3. ALMACENAMIENTO
   Navegador guarda la cookie asociada al dominio.

4. PETICIONES FUTURAS (automático)
   Cliente  →  GET /dashboard  +  Cookie: session_id=abc123  →  Servidor

5. RECONOCIMIENTO
   Servidor lee la cookie, valida session_id, identifica al usuario.
   Sin preguntar usuario/contraseña de nuevo.
```

---

## Anatomía de una Cookie

### Header Set-Cookie completo

```
Set-Cookie: nombre=valor; atributo1; atributo2=valor2; ...
```

**Ejemplo real:**

```
Set-Cookie: session_id=abc123; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=3600; Domain=miapp.com
```

### Atributos — Referencia Completa

|Atributo|Descripción|Impacto en Seguridad|
|---|---|---|
|`nombre=valor`|Par clave-valor. El valor debe ser URL-encoded si contiene caracteres especiales|—|
|`Max-Age=N`|Segundos hasta expiración. `0` o negativo = eliminar inmediatamente|Define ventana de ataque|
|`Expires=fecha`|Fecha absoluta de expiración (GMT). Menos preciso que Max-Age|Igual que Max-Age|
|`Path=/ruta`|La cookie solo se envía a URLs que comiencen con esta ruta|Scope de envío|
|`Domain=dominio`|Dominios que reciben la cookie. Si se omite: solo el dominio exacto|No usar `Domain=` para subdominios de terceros|
|`Secure`|Solo se envía por HTTPS. Nunca por HTTP|**Crítico** — previene intercepción|
|`HttpOnly`|No accesible desde JavaScript (`document.cookie`). Solo HTTP|**Crítico** — previene robo por XSS|
|`SameSite=valor`|Controla envío en peticiones cross-site (ver detalle abajo)|**Crítico** — previene CSRF|

### SameSite — Detalle

```
SameSite=Strict
  La cookie NUNCA se envía en peticiones cross-site.
  Máxima protección CSRF.
  Inconveniente: Si el usuario llega desde un enlace externo, no tendrá sesión
  y deberá hacer login aunque ya estuviera autenticado.
  Usar para: operaciones sensibles, administración, banca.

SameSite=Lax  (default en navegadores modernos si se omite)
  La cookie se envía en navegación de nivel superior (clic en enlace → GET).
  NO se envía en recursos embebidos, iframes, fetch/XHR cross-origin.
  Buen balance seguridad/usabilidad para la mayoría de apps.

SameSite=None
  La cookie se envía en todos los contextos cross-site.
  REQUIERE obligatoriamente: Secure
  Usar solo para: integraciones OAuth, widgets embebidos, SSO entre subdominios.
  Es el valor más permisivo — usar con extremo cuidado.
```

---

## Tipos de Cookies

### Por duración

```
SESSION (de sesión)
  Sin atributo Max-Age ni Expires.
  Se elimina cuando el navegador se cierra.
  Uso: sesiones de autenticación temporales.

PERSISTENT (persistentes)
  Con Max-Age o Expires definido.
  Persisten entre sesiones del navegador.
  Uso: "recordarme", preferencias de usuario, analytics.
```

### Por propósito

|Tipo|Propósito|Consideración Legal|
|---|---|---|
|**Esenciales**|Sesión, autenticación, carrito de compras|Exentas de consentimiento (GDPR)|
|**Preferencias**|Idioma, tema, configuración UI|Requieren consentimiento|
|**Analytics**|Comportamiento del usuario, métricas|Requieren consentimiento|
|**Marketing**|Tracking, publicidad personalizada|Requieren consentimiento explícito|

---

## Cookies vs otras formas de almacenamiento

|Característica|Cookie|localStorage|sessionStorage|
|---|---|---|---|
|Tamaño máximo|~4 KB|~5–10 MB|~5–10 MB|
|Enviado al servidor|✅ Automático en cada request|❌ No|❌ No|
|Accesible desde JS|⚠️ Solo si no es HttpOnly|✅ Siempre|✅ Siempre|
|Persiste entre pestañas|✅ Sí|✅ Sí|❌ No (por pestaña)|
|Persiste entre sesiones|⚠️ Solo si Persistent|✅ Sí|❌ No|
|Control de expiración|✅ Max-Age / Expires|❌ Manual en JS|❌ Automático al cerrar pestaña|
|Protección XSS|✅ Con HttpOnly|❌ No|❌ No|
|Protección CSRF|⚠️ Requiere SameSite|✅ No se envía sola|✅ No se envía sola|
|Uso ideal|Sesiones, auth|Preferencias, estado UI|Estado temporal de flujo|

---

## Seguridad — Amenazas y Mitigaciones

### XSS (Cross-Site Scripting) → Robo de Cookie

```
ATAQUE:
  El atacante inyecta JavaScript malicioso en la página.
  El script lee document.cookie y exfiltra la cookie de sesión.
  El atacante usa la cookie robada para suplantar al usuario.

MITIGACIÓN:
  ✅ HttpOnly — la cookie es invisible para JavaScript.
  ✅ Content-Security-Policy (CSP) header — limita scripts ejecutables.
  ✅ Validación y sanitización de inputs en servidor.
```

### CSRF (Cross-Site Request Forgery) → Petición falsa con cookie

```
ATAQUE:
  El usuario está autenticado en banco.com.
  El atacante le hace visitar malicioso.com que tiene un form:
    <form action="https://banco.com/transferir" method="POST">
  El navegador envía automáticamente la cookie de banco.com.
  El banco procesa la transferencia creyendo que es legítima.

MITIGACIONES:
  ✅ SameSite=Strict o Lax — la cookie no se envía en peticiones cross-site.
  ✅ CSRF Token — token único por formulario, verificado en servidor.
  ✅ Verificar header Origin / Referer en peticiones de escritura.
  ✅ Re-autenticación para operaciones críticas.
```

### Session Hijacking → Robo de ID de sesión

```
ATAQUE:
  El atacante intercepta el tráfico HTTP y obtiene la cookie de sesión.
  Usa la cookie para acceder como el usuario legítimo.

MITIGACIONES:
  ✅ Secure — la cookie solo viaja por HTTPS (nunca HTTP).
  ✅ HTTPS obligatorio en toda la aplicación.
  ✅ Regenerar session_id después del login (previene session fixation).
  ✅ Tiempo de expiración razonable (no sesiones eternas).
```

### Cookie Theft via Subdomain

```
ATAQUE:
  Si Domain=miapp.com, la cookie se envía a TODOS los subdominios.
  Un subdominio comprometido (blog.miapp.com) puede leer/usar la cookie.

MITIGACIÓN:
  ✅ Omitir atributo Domain (solo el dominio exacto recibe la cookie).
  ✅ Si se necesitan subdominios: listar explícitamente y usar __Host- prefix.
```

---

## Prefijos de Cookie (Security Prefixes)

Los prefijos son convenciones del nombre que los navegadores modernos aplican como restricciones:

```
__Secure-nombre=valor
  REQUIERE: Secure
  Garantiza que solo se establece por HTTPS.
  Ejemplo: __Secure-session_id=abc123

__Host-nombre=valor
  REQUIERE: Secure + Path=/ + sin Domain
  Máxima seguridad: solo el host exacto, por HTTPS, en toda la app.
  Ejemplo: __Host-csrf_token=xyz789
```

---

## Gestión de Sesiones con Cookies

### Flujo completo de autenticación

```
LOGIN:
  1. Cliente envía credenciales (POST /login)
  2. Servidor valida credenciales
  3. Servidor crea sesión → genera session_id único (UUID v4, criptográficamente seguro)
  4. Servidor guarda sesión en store (Redis, DB): { session_id → { user_id, roles, created_at } }
  5. Servidor responde:
     Set-Cookie: session_id=<uuid>; HttpOnly; Secure; SameSite=Lax; Max-Age=3600; Path=/

PETICIÓN AUTENTICADA:
  1. Navegador envía automáticamente: Cookie: session_id=<uuid>
  2. Servidor busca session_id en el store
  3. Si existe y no expiró → usuario autenticado → continuar
  4. Si no existe o expiró → 401 Unauthorized → redirigir a login

LOGOUT:
  1. Servidor elimina la sesión del store: DELETE session:<uuid>
  2. Servidor responde:
     Set-Cookie: session_id=; Max-Age=0; Path=/; HttpOnly; Secure
     (Max-Age=0 instruye al navegador a eliminar la cookie inmediatamente)
  3. Redirigir a página de login
```

### Session Store — Opciones

|Store|Ventajas|Desventajas|Uso recomendado|
|---|---|---|---|
|**Memoria del proceso**|Ultra rápido, sin configuración|No compartido entre instancias, se pierde al reiniciar|Solo desarrollo|
|**Redis**|Rápido, distribuido, TTL nativo, escalable|Dependencia externa|Producción (recomendado)|
|**Base de datos**|Persistente, auditable|Más lento, carga en DB|Cuando auditoría es requerida|
|**JWT en cookie**|Stateless, sin store|Revocación compleja, tamaño mayor|APIs con múltiples servicios|

---

## Buenas Prácticas

### ✅ Siempre

```
1. HttpOnly en cookies de sesión/auth — protección XSS.
2. Secure en producción — cookies solo por HTTPS.
3. SameSite=Lax como mínimo; Strict para operaciones sensibles.
4. Max-Age con tiempo razonable — no sesiones eternas.
5. Path=/ especificado explícitamente.
6. Regenerar session_id después del login exitoso (previene session fixation).
7. HTTPS obligatorio en toda la aplicación.
```

### ❌ Nunca

```
1. Almacenar contraseñas o datos sensibles en el valor de la cookie.
2. Usar HTTP (sin S) con cookies de autenticación.
3. Session IDs predecibles o secuenciales (deben ser UUID/random).
4. Omitir expiración en cookies persistentes.
5. Domain=.miapp.com si no es necesario (amplía superficie de ataque).
6. SameSite=None sin Secure.
7. Confiar en el valor de la cookie sin validarlo en el servidor.
```

---

## Headers de Respuesta — Ejemplos Completos

### Cookie de sesión segura (máxima seguridad)

```
Set-Cookie: __Host-session_id=<uuid-v4>;
            Path=/;
            Secure;
            HttpOnly;
            SameSite=Strict;
            Max-Age=1800
```

### Cookie de preferencias (no sensible)

```
Set-Cookie: idioma=es;
            Path=/;
            SameSite=Lax;
            Max-Age=31536000
```

### Cookie para SSO / OAuth cross-domain

```
Set-Cookie: oauth_state=<token>;
            Path=/auth;
            Secure;
            HttpOnly;
            SameSite=None;
            Max-Age=300
```

### Eliminar cookie

```
Set-Cookie: session_id=;
            Path=/;
            Max-Age=0;
            Secure;
            HttpOnly
```

---

## Checklist de Implementación

### Seguridad

- [ ] `HttpOnly` en todas las cookies de sesión y autenticación
- [ ] `Secure` habilitado en producción
- [ ] `SameSite` definido explícitamente (Strict o Lax según caso)
- [ ] HTTPS obligatorio en todos los endpoints
- [ ] Session ID es UUID v4 o equivalente criptográficamente seguro
- [ ] Session ID se regenera después del login exitoso
- [ ] Sesiones se invalidan en el servidor al hacer logout

### Privacidad y Compliance

- [ ] Cookies clasificadas: esenciales / preferencias / analytics / marketing
- [ ] Consentimiento solicitado para cookies no esenciales (GDPR/LGPD)
- [ ] Política de cookies documentada y accesible
- [ ] Datos sensibles nunca en el valor de la cookie

### Expiración

- [ ] `Max-Age` o `Expires` definido en todas las cookies persistentes
- [ ] Tiempo de expiración apropiado para el tipo de cookie
- [ ] Proceso de logout elimina la cookie correctamente (Max-Age=0)

### Operacional

- [ ] Session store con capacidad de invalidación manual (emergencias)
- [ ] Logs de creación y destrucción de sesiones
- [ ] Monitoreo de sesiones activas

---

> **COOKIE = Memoria + Experiencia + Seguridad + Personalización**  
> Una cookie bien configurada es invisible para el usuario y robusta ante ataques.