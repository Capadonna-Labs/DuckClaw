# Guía de Configuración: DuckClaw Gateway & Tailscale Funnel

Esta documentación detalla los pasos para exponer el servicio local del bot (puerto 8000) a internet de forma segura utilizando **Tailscale Funnel**, permitiendo que Telegram envíe webhooks a la Mac Mini de forma exitosa.

## 1. Verificación de Puertos Locales
Antes de configurar el túnel, es necesario identificar en qué puerto está escuchando realmente la aplicación Python.

```bash
# Listar procesos Python que están escuchando puertos
lsof -iTCP -sTCP:LISTEN -P | grep -i "python"

# Verificar específicamente un puerto (ej. 8000)
lsof -i :8000
```

## 2. Configuración de Tailscale Funnel
Para las versiones actuales de Tailscale en macOS, se utiliza el comando simplificado. El objetivo es mapear el tráfico HTTPS público (puerto 443) al puerto local de la aplicación.

### Reiniciar configuración (Opcional, en caso de error)
Si existe una configuración previa errónea, se recomienda limpiar:
```bash
tailscale serve reset
```

### Activar el Funnel en segundo plano
Este comando activa el proxy público y lo mantiene ejecutándose aunque se cierre la terminal:
```bash
tailscale funnel --bg 8000
```

### Verificar el estado del túnel
Para confirmar que la URL pública está activa y apuntando al puerto correcto:
```bash
tailscale funnel status
```
**Resultado esperado:**
- `https://mac-mini-de-ai.tail010cbd.ts.net/`
- `|-- proxy http://127.0.0.1:8000`

---

## 3. Pruebas de Conectividad
Es crucial verificar el acceso desde una red externa (fuera de la red de Tailscale) para asegurar que el Webhook de Telegram funcionará.

1. **Ruta de Documentación:** Abrir en un navegador (usando datos móviles): 
   `https://mac-mini-de-ai.tail010cbd.ts.net/docs`
2. **Respuesta exitosa:** Debería cargar la interfaz de Swagger UI o FastAPI.

---

## 4. Gestión de Base de Datos (DBeaver)
Operaciones para asegurar la integridad de la base de datos durante el desarrollo.

### Backup (Exportar)
1. En DBeaver, haz clic derecho sobre la base de datos o esquema.
2. Selecciona **Herramientas (Tools)** > **Dump database**.
3. Configura la ruta de salida y presiona **Start**.
   *Nota: Se recomienda guardar el archivo `.sql` con la fecha actual.*

### Importar (Restaurar)
1. Crea una base de datos vacía en el servidor destino.
2. Clic derecho sobre la base de datos > **Herramientas (Tools)** > **Restore database**.
3. Selecciona el archivo de backup previo y presiona **Start**.

---

## 5. Notas de Seguridad
* **Secret Token:** Al configurar el webhook en Telegram, se recomienda usar el parámetro `secret_token` para validar que las peticiones provengan únicamente de servidores oficiales de Telegram.
* **Apagar el acceso:** Si se requiere suspender el acceso público temporalmente:
  ```bash
  tailscale funnel --https=443 off
  ```

---
**Última actualización:** Mayo 2024
**Responsable:** Workstation Mac Mini AI