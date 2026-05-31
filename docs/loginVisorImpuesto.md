# SDD - Seguridad de Login en Visor Impuesto

## 1. Objetivo

Documentar cómo se realiza actualmente el login en Visor Impuesto/Visor 360, qué controles de seguridad existen y qué buenas prácticas se pueden reutilizar en otro proyecto institucional.

El análisis cubre:

- Flujo de autenticación ciudadano, funcionario y API.
- Límites por IP y rate limiting.
- Protección frente a SQL injection.
- Protección frente a XSS.
- Seguridad de sesión, cookies, CSRF, roles y permisos.
- Recomendaciones de implementación para un nuevo proyecto.

## 2. Resumen ejecutivo

El repositorio tiene una base sólida de seguridad por apoyarse en Laravel:

- Middleware `web` con sesión, cookies cifradas y CSRF.
- Autenticación basada en sesión para web.
- LDAP/local para funcionarios.
- UME/local para ciudadanos.
- JWT/Sanctum para APIs.
- Hashing nativo de contraseñas.
- Roles/permisos con Spatie.
- Uso mayoritario de Eloquent/query builder.
- Sanitización HTML especializada en módulos DAP con `DOMPurify` y `HTMLPurifier`.

La brecha principal detectada es que no se observa un `throttle` explícito para los endpoints de login web ciudadano y servidor LDAP. También conviene reforzar cabeceras HTTP de seguridad globales.

## 3. Archivos relevantes

### Autenticación web

- `routes/web.php`
- `app/Http/Controllers/Auth/LoginController.php`
- `app/Services/AuthService.php`
- `app/Services/UmeService.php`
- `resources/views/auth/login.blade.php`
- `resources/views/auth/choice.blade.php`

### Autenticación funcionario LDAP/local

- `app/Http/Controllers/Auth_ldap/AuthLDAPController.php`
- `app/Services/Auth_ldap/AuthLDAPService.php`
- `resources/views/auth_ldap/login.blade.php`
- `config/ldap.php`

### Autenticación API

- `routes/api.php`
- `routes/api/auth/auth_ldap.php`
- `app/Http/Controllers/Auth/ApiAuthController.php`
- `app/Http/Controllers/Api/AuthController.php`
- `app/Http/Middleware/JwtMiddleware.php`
- `config/sanctum.php`
- `config/auth.php`

### Seguridad transversal

- `app/Http/Kernel.php`
- `app/Providers/RouteServiceProvider.php`
- `app/Http/Middleware/VerifyCsrfToken.php`
- `config/session.php`
- `config/cors.php`
- `app/Models/User.php`
- `app/Models/Base/UserModel.php`
- `app/Services/DepartamentoAdministrativoPlaneacion/Tramites/HtmlStorageSanitizerService.php`
- `resources/js/components/EditorDocumentosTecnicos/core/wordPaste.js`
- `DocumentationVisorDoc360/03-Modulos/DepartamentoAdministrativoPlaneacion/Tramites/01-Manual-Core/15-seguridad-y-cicd.md`

## 4. Flujo actual de login

### 4.1 Selección de tipo de usuario

Ruta:

- `GET /statements/choice`

Controlador:

- `App\Http\Controllers\Auth\NewInterface@login`

Vista:

- `resources/views/auth/choice.blade.php`

El usuario escoge si ingresa como:

- Ciudadano.
- Servidor/funcionario.

### 4.2 Login ciudadano

Ruta generada por `Auth::routes()` dentro del prefijo `statements`:

- `GET /statements/login`
- `POST /statements/login`

Controlador:

- `App\Http\Controllers\Auth\LoginController`

Vista:

- `resources/views/auth/login.blade.php`

Campos del formulario:

- `username`
- `password`
- `remember`

Controles visibles:

- `@csrf` en el formulario.
- `autocomplete="username"` en usuario.
- Password con `type="password"`.
- Errores renderizados con `{{ }}`, escapados por Blade.

Flujo técnico:

1. El formulario POST llega a `LoginController@login()`.
2. El método usa `LoginRequest`, pero el archivo no fue accesible por permisos del entorno.
3. `LoginController` delega en `AuthService@login()`.
4. `AuthService` decide si autentica contra base local o UME.
5. Si el usuario es `visor360` o está en usuarios de prueba UME, usa `loginFromDatabase()`.
6. Para usuarios normales, usa `loginFromUme()`.
7. Si el login es exitoso, registra/actualiza usuario local, ejecuta `Auth::login($user)`, asigna rol `CIUDADANO` y guarda `auth_type = ume`.
8. Redirige a `RouteServiceProvider::HOME`, que actualmente es `/statements/home`.

### 4.3 Login funcionario

Rutas:

- `GET /statements/auth-func`
- `POST /statements/auth-ldap`

Controlador:

- `App\Http\Controllers\Auth_ldap\AuthLDAPController`

Servicio:

- `App\Services\Auth_ldap\AuthLDAPService`

Vista:

- `resources/views/auth_ldap/login.blade.php`

Campos:

- `username`
- `password`
- `remember`

Flujo técnico:

1. El formulario POST llega a `AuthLDAPController@authenticate`.
2. El controlador delega en `AuthLDAPService@handleAuthentication`.
3. Se validan campos `username` y `password` como requeridos y string.
4. Si `LDAP_ENABLED=false`, se usa autenticación local de Laravel.
5. Si LDAP está habilitado, busca el usuario por `samaccountname` o `uid`.
6. Valida credenciales contra LDAP.
7. Si el usuario LDAP existe pero no está registrado localmente, redirige a registro.
8. Si existe localmente, ejecuta `Auth::login($ldapUser)`.
9. Regenera sesión.
10. Remueve rol `CIUDADANO` si aplica.
11. Asigna rol `FUNCIONARIO`.
12. Guarda `auth_type = ldap`.
13. Redirige a `/statements/home`.

### 4.4 Login API LDAP/JWT

Ruta:

- `POST /statements/api/auth/login`

Controlador:

- `App\Http\Controllers\Auth\ApiAuthController`

Flujo:

1. Valida `username` y `password`.
2. Reutiliza `AuthLDAPService@authenticate`.
3. Si el usuario es válido, genera JWT con `JWTAuth::fromUser($user)`.
4. Retorna `access_token`, `token_type`, `expires_in` y `user`.

### 4.5 Login API email/password

Ruta:

- `POST /statements/api/login`

Controlador:

- `App\Http\Controllers\Api\AuthController`

Flujo:

1. Toma `email` y `password`.
2. Ejecuta `JWTAuth::attempt($credentials)`.
3. Si es correcto, retorna token y usuario.
4. Rutas protegidas usan middleware `jwt.auth`.

## 5. Seguridad actual

### 5.1 CSRF

Estado: activo para web.

Evidencia:

- `app/Http/Kernel.php` incluye `VerifyCsrfToken` en el grupo `web`.
- Los formularios de login ciudadano y funcionario usan `@csrf`.
- `config/sanctum.php` también referencia `VerifyCsrfToken`.

Riesgo:

- `VerifyCsrfToken` tiene excepciones manuales para algunos endpoints.
- Las excepciones deben revisarse periódicamente para evitar POST públicos no justificados.

Buena práctica reutilizable:

- Todo formulario web mutable debe usar CSRF.
- Las APIs públicas deben usar otro mecanismo claro: token, firma, JWT, API key o rate limit fuerte.

### 5.2 Rate limiting y límites por IP

Estado: parcial.

Evidencia:

- `app/Providers/RouteServiceProvider.php` define:

```php
RateLimiter::for('api', function (Request $request) {
    return Limit::perMinute(60)->by($request->user()?->id ?: $request->ip());
});
```

- `app/Http/Kernel.php` aplica `ThrottleRequests:api` al grupo `api`.
- `VerificationController` usa `throttle:6,1` para verificación de email.

Brecha:

- No se observó `throttle` explícito en:
  - `POST /statements/login`
  - `POST /statements/auth-ldap`
  - `POST /statements/api/login`
  - `POST /statements/api/auth/login`
- `LoginController` sobrescribe `login()`. Aunque usa el trait `AuthenticatesUsers`, al sobrescribir el método no se evidencia que se ejecute el throttling estándar del trait.

Recomendación:

- Definir rate limit específico de login por usuario normalizado + IP.
- Ejemplo conceptual:

```php
RateLimiter::for('login', function (Request $request) {
    $username = strtolower((string) $request->input('username', $request->input('email', '')));

    return Limit::perMinute(5)->by($username.'|'.$request->ip());
});
```

- Aplicar:

```php
Route::post('/login', [LoginController::class, 'login'])
    ->middleware('throttle:login');
```

Para otro proyecto:

- Login web: 5 intentos por minuto por usuario + IP.
- Recuperación de contraseña: 3 intentos por minuto por IP.
- API login: 5 intentos por minuto por IP + cliente.
- API general autenticada: 60/min o según criticidad.
- Agregar bloqueo progresivo o cooldown cuando haya muchos fallos.

### 5.3 Sesión y cookies

Estado: bueno con ajustes recomendados.

Evidencia:

- `AuthService@loginFromDatabase()` regenera sesión con `request()->session()->regenerate()`.
- `AuthLDAPService` regenera sesión en login exitoso.
- `LoginController@logout()` ejecuta:
  - `guard()->logout()`
  - `session()->flush()`
  - `session()->invalidate()`
  - `session()->regenerateToken()`
  - `session()->save()`
- `config/session.php` define:
  - `http_only = true`
  - `same_site = lax`
  - `secure = env('SESSION_SECURE_COOKIE')`
  - `lifetime = 120`

Recomendación:

- En producción, `SESSION_SECURE_COOKIE=true`.
- Evaluar `SESSION_ENCRYPT=true` si se almacena información sensible en sesión.
- Mantener `http_only=true`.
- Mantener `same_site=lax` o usar `strict` si no hay flujos cross-site.
- Evitar guardar datos sensibles en sesión.

### 5.4 Contraseñas

Estado: bueno.

Evidencia:

- `app/Models/User.php` tiene cast:

```php
'password' => 'hashed',
```

- `UserModel::saveUser()` usa `bcrypt()` al crear usuario.
- `ResetPasswordController` usa `Hash::make()`.

Riesgo:

- En `AuthService@registerOrUpdateUserFromUme()`, si el usuario no existe, se guarda password local usando la contraseña enviada a UME. Aunque se hashea, conviene revisar si realmente el sistema debe conservar un hash local de una credencial externa.

Recomendación:

- En integraciones externas como UME/LDAP, evitar persistir contraseñas de sistemas externos salvo que exista una razón funcional clara.
- Preferir identidad federada o usuario local sin password si el login siempre depende del proveedor externo.

### 5.5 Autorización y control de acceso

Estado: bueno.

Evidencia:

- Uso de middleware `auth`.
- Uso de Spatie Permission:
  - `role`
  - `permission`
  - `role_or_permission`
- Middleware propio `check.login` valida `auth_type`.
- Roles funcionales:
  - `CIUDADANO`
  - `FUNCIONARIO`
  - Roles DAP por flujo.

Buenas prácticas reutilizables:

- Separar autenticación de autorización.
- Guardar tipo de autenticación cuando el proyecto mezcla fuentes: `ldap`, `ume`, `local`.
- Usar roles institucionales explícitos.
- Validar rol en rutas y reglas finas en Policies/Gates cuando aplique.

### 5.6 SQL injection

Estado: mayormente cubierto.

Evidencia:

- El login usa Eloquent:
  - `User::where('identification_nit', $username)->first()`
  - `Auth::attempt(...)`
  - `UserModel::findUserByIdentification(...)`
- Las búsquedas LDAP usan API de `ldaprecord`.
- En el repo predominan Eloquent y query builder.
- En varios `whereRaw` revisados se usan placeholders:

```php
whereRaw('unaccent("name_ume") ILIKE unaccent(?)', ['%' . $name_ume . '%'])
```

Riesgos:

- Existen consultas `DB::raw`, `selectRaw`, `orderByRaw`, `whereRaw` en distintos módulos.
- `raw` no es inseguro por sí mismo, pero es riesgoso si interpola input del usuario.

Reglas recomendadas para otro proyecto:

- Usar Eloquent/query builder por defecto.
- Si se usa `whereRaw`, usar placeholders `?` y bindings.
- Nunca concatenar input del usuario en SQL.
- Para columnas dinámicas de ordenamiento, usar allowlist:

```php
$allowedSorts = ['created_at', 'name', 'status'];
$sort = in_array($request->sort, $allowedSorts, true) ? $request->sort : 'created_at';
```

- Validar tipos en FormRequest antes de consultar.
- Para tablas fuera de la conexión por defecto, calificar conexión/esquema de forma explícita.

### 5.7 XSS

Estado: bueno en login, parcial a nivel global.

Evidencia positiva:

- Vistas de login usan `{{ }}` para errores y valores, lo cual escapa HTML.
- Assets se generan con `asset()` y rutas con `route()`.
- En módulos DAP hay sanitización fuerte para HTML enriquecido:
  - Frontend: `DOMPurify` en `wordPaste.js`.
  - Backend: `HTMLPurifier` en `HtmlStorageSanitizerService`.

El servicio backend usa allowlist cerrada de etiquetas, atributos y propiedades CSS. También elimina manejadores `on*` en imágenes y remueve `file://`.

Riesgos:

- Existen usos de `{!! !!}` en componentes genéricos como:
  - `resources/views/components/ui/empty-state.blade.php`
  - `resources/views/components/ui/info-item.blade.php`
- Esos puntos solo son seguros si reciben HTML confiable o previamente sanitizado.

Reglas recomendadas:

- Usar `{{ }}` por defecto.
- Prohibir `{!! !!}` salvo componentes documentados que reciban HTML sanitizado.
- Sanitizar HTML antes de persistir y antes de renderizar si viene de usuario.
- Usar allowlist, no blacklist.
- Agregar CSP para reducir impacto de XSS residual.

### 5.8 Cabeceras HTTP de seguridad

Estado: brecha.

No se observó un middleware global para:

- `Content-Security-Policy`
- `Strict-Transport-Security`
- `X-Frame-Options`
- `X-Content-Type-Options`
- `Referrer-Policy`
- `Permissions-Policy`

Solo se vio un uso puntual de `X-Frame-Options: SAMEORIGIN` en un controlador de borradores.

Recomendación:

Crear middleware global de cabeceras:

```php
return $next($request)
    ->headers->set('X-Content-Type-Options', 'nosniff');
```

Política mínima recomendada:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- `Strict-Transport-Security` solo en HTTPS productivo.
- `Content-Security-Policy` ajustada a Vite/CDNs reales.

### 5.9 CORS

Estado: revisar por ambiente.

Evidencia:

- `config/cors.php` define paths:
  - `api/*`
  - `sanctum/csrf-cookie`
  - `statements/api/*`
  - `statements/*`
  - `hacienda/*`
- `supports_credentials = true`.
- Hay lista de orígenes locales y dominios de Medellín.

Riesgo:

- CORS con credenciales debe ser estricto.
- Evitar abrir `statements/*` si no todos los endpoints requieren cross-origin.

Recomendación:

- Separar CORS por ambiente.
- No usar wildcard con credentials.
- Limitar paths cross-origin a APIs reales.
- Revisar orígenes con y sin trailing slash.

### 5.10 Logs y auditoría

Estado: parcial.

Evidencia:

- Hay logs de login exitoso/fallido en `AuthService` y `AuthLDAPService`.
- Se registra usuario y tipo de autenticación.

Riesgo:

- Evitar loguear respuestas completas de proveedores externos si contienen datos personales.
- Evitar mensajes que permitan enumerar usuarios.

Recomendación:

- Registrar:
  - usuario normalizado o hash del usuario,
  - IP,
  - user-agent,
  - resultado,
  - proveedor,
  - motivo genérico,
  - timestamp.
- No registrar contraseñas, tokens ni payloads completos con PII.

## 6. Bondades reutilizables del repositorio

### 6.1 Separación por servicios

El login no queda completamente dentro del controller. El controller delega en servicios:

- `AuthService`
- `AuthLDAPService`
- `UmeService`

Esto permite aislar:

- HTTP.
- Proveedor externo.
- Persistencia local.
- Roles.
- Sesión.

### 6.2 Mezcla controlada de fuentes de identidad

El sistema soporta:

- UME para ciudadanos.
- LDAP para funcionarios.
- Local para usuarios especiales o fallback.
- JWT/Sanctum para API.

La variable de sesión `auth_type` permite diferenciar flujos.

### 6.3 Sesión regenerada correctamente

Regenerar sesión al autenticar reduce riesgo de session fixation.

### 6.4 Roles institucionales

Spatie Permission permite centralizar acceso por roles y permisos.

### 6.5 Sanitización HTML madura en DAP

El patrón `DOMPurify` en frontend + `HTMLPurifier` en backend es una práctica fuerte para módulos donde se pega o edita HTML enriquecido.

### 6.6 Documentación de seguridad

La documentación DAP ya define principios:

- Validación por capas.
- CSRF activo.
- Sanitización.
- SQL binding.
- Transacciones para operaciones críticas.

## 7. SDD para nuevo proyecto

### 7.1 Alcance

Diseñar un módulo de autenticación institucional seguro para web y API, con soporte para usuarios ciudadanos, funcionarios y clientes API.

### 7.2 Actores

- Ciudadano.
- Funcionario.
- Administrador.
- Cliente API.
- Servicio externo de identidad.

### 7.3 Requisitos funcionales

- Permitir login web con usuario/documento y contraseña.
- Permitir login funcionario por LDAP o proveedor institucional.
- Permitir login API por JWT o Sanctum.
- Permitir logout seguro.
- Redirigir por rol o tipo de autenticación.
- Asignar rol inicial según proveedor.
- Registrar auditoría de intentos exitosos y fallidos.

### 7.4 Requisitos no funcionales de seguridad

- CSRF obligatorio en web.
- Rate limit específico para login.
- Contraseñas con hash nativo de Laravel.
- Sesión regenerada al autenticar.
- Sesión invalidada al cerrar.
- Cookies `httpOnly`, `secure` en producción y `sameSite`.
- Respuestas de error genéricas.
- Logs sin secretos.
- Consultas con Eloquent/query builder o bindings.
- Sanitización de HTML enriquecido.
- Cabeceras HTTP de seguridad.

### 7.5 Arquitectura propuesta

Capas:

- Presentación:
  - `LoginController`
  - `LoginRequest`
  - vistas Blade o frontend SPA
- Aplicación:
  - `AuthenticateUserService`
  - `LogoutUserService`
  - `LoginRateLimitPolicy`
  - `LoginAuditService`
- Dominio:
  - `AuthenticatedIdentity`
  - `AuthProvider`
  - reglas de rol inicial
- Infraestructura:
  - `LdapIdentityProvider`
  - `UmeIdentityProvider`
  - `LocalIdentityProvider`
  - repositorios Eloquent

### 7.6 Flujo objetivo de login web

1. Usuario abre pantalla de login.
2. Frontend envía POST con CSRF.
3. Middleware `throttle:login` evalúa usuario + IP.
4. `LoginRequest` valida estructura.
5. Controller delega a `AuthenticateUserService`.
6. Servicio normaliza usuario.
7. Servicio consulta proveedor correspondiente.
8. Si falla, registra auditoría y responde error genérico.
9. Si es exitoso:
   - sincroniza usuario local,
   - asigna rol inicial,
   - ejecuta `Auth::login`,
   - regenera sesión,
   - guarda `auth_type`,
   - registra auditoría,
   - redirige.

### 7.7 Flujo objetivo de logout

1. Usuario envía POST logout con CSRF.
2. Controller ejecuta `Auth::logout()`.
3. Invalida sesión.
4. Regenera token CSRF.
5. Redirige a pantalla pública.

### 7.8 Rate limiting recomendado

| Endpoint | Límite |
| --- | --- |
| Web login | 5 intentos/minuto por usuario + IP |
| LDAP login | 5 intentos/minuto por usuario + IP |
| API login | 5 intentos/minuto por IP + cliente |
| Recuperación contraseña | 3 intentos/minuto por IP |
| API autenticada general | 60 intentos/minuto por usuario o IP |

### 7.9 Modelo de auditoría recomendado

Tabla sugerida: `login_attempts`

Campos:

- `id`
- `username_hash`
- `user_id`
- `provider`
- `ip_address`
- `user_agent`
- `successful`
- `failure_reason`
- `created_at`

Reglas:

- No guardar password.
- No guardar tokens.
- No guardar payload completo del proveedor externo.
- Usar hash del username cuando haya PII sensible.

### 7.10 Cabeceras recomendadas

Agregar middleware global:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- `Strict-Transport-Security` en producción HTTPS.
- `Content-Security-Policy` ajustada al frontend real.

### 7.11 Reglas anti SQL injection

- Prohibido concatenar input en SQL.
- Usar bindings en cualquier `raw`.
- Usar allowlists para columnas dinámicas.
- Usar FormRequest para tipos y rangos.
- Encapsular consultas complejas en Query Objects o repositorios.

### 7.12 Reglas anti XSS

- Blade debe usar `{{ }}` por defecto.
- `{!! !!}` solo con HTML purificado.
- Sanitizar HTML rico en backend antes de persistir.
- Sanitizar HTML pegado en frontend cuando exista editor enriquecido.
- Definir allowlist de etiquetas, atributos y CSS.
- Agregar CSP.

## 8. Checklist de implementación

- [ ] Login web protegido con CSRF.
- [ ] Login web protegido con `throttle:login`.
- [ ] Login API protegido con rate limiter dedicado.
- [ ] Sesión regenerada después de login.
- [ ] Sesión invalidada después de logout.
- [ ] Cookies `secure=true` en producción.
- [ ] Errores de login genéricos.
- [ ] Auditoría de intentos de login.
- [ ] Logs sin secretos ni PII innecesaria.
- [ ] Roles asignados por proveedor.
- [ ] Rutas protegidas con `auth` y `role/permission`.
- [ ] Consultas sin interpolación de input.
- [ ] HTML enriquecido sanitizado.
- [ ] Cabeceras HTTP de seguridad.
- [ ] CORS restringido por ambiente.
- [ ] Tests de login exitoso.
- [ ] Tests de credenciales inválidas.
- [ ] Tests de rate limit.
- [ ] Tests de CSRF.
- [ ] Tests de logout.
- [ ] Tests de acceso por rol.

## 9. Riesgos priorizados

### Alto

- Falta de rate limit explícito en login web y LDAP.
- Falta de cabeceras HTTP globales de seguridad.

### Medio

- CORS amplio con credenciales.
- Uso de `{!! !!}` fuera de componentes estrictamente sanitizados.
- Logs con potencial exceso de datos de proveedor externo.

### Bajo

- Dependencia de configuración ambiental para `SESSION_SECURE_COOKIE`.
- Endpoints CSRF exceptuados que requieren revisión periódica.

## 10. Conclusión

Visor Impuesto tiene buenas bases para tomar como referencia: Laravel session auth, CSRF, hashing, roles Spatie, servicios de autenticación separados y sanitización HTML avanzada en DAP.

Para otro proyecto, se recomienda copiar la arquitectura por capas y servicios, pero reforzar desde el inicio:

- Rate limiting dedicado para login.
- Middleware de security headers.
- Auditoría estructurada de intentos.
- CORS estricto.
- Política clara de HTML seguro.
- Tests de seguridad como parte del flujo de entrega.
