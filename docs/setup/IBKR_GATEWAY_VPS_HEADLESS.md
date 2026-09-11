# IBKR Gateway Setup en VPS (Headless Linux)

**Target**: VPS Linux sin GUI (root@100.75.4.17)  
**Objetivo**: Ejecutar IB Gateway en modo headless para bracket orders  
**Fecha**: 2026-09-11

---

## 📋 Requisitos

- VPS Linux (Ubuntu/Debian recomendado)
- Java 11+ instalado
- Xvfb (X Virtual Framebuffer) para GUI headless
- Cuenta IBKR (paper o live)
- SSH access con Tailscale

---

## 🔧 Instalación

### 1. Instalar Java 11+

```bash
ssh root@100.75.4.17

# Verificar Java
java -version

# Si no está instalado:
sudo apt update
sudo apt install -y openjdk-11-jre-headless

# Verificar
java -version
# Debería mostrar: openjdk version "11.x.x" o superior
```

### 2. Instalar Xvfb y dependencias GUI

```bash
# Xvfb = X Virtual Frame Buffer (GUI headless)
sudo apt install -y xvfb x11vnc fluxbox

# Verificar
which Xvfb
# Debería mostrar: /usr/bin/Xvfb
```

### 3. Descargar IB Gateway (Standalone)

```bash
cd /root
wget https://download2.interactivebrokers.com/installers/ibgateway/latest-standalone/ibgateway-latest-standalone-linux-x64.sh

# Hacer ejecutable
chmod +x ibgateway-latest-standalone-linux-x64.sh

# Instalar (sin GUI)
./ibgateway-latest-standalone-linux-x64.sh -q

# Instalación típica en:
# /root/Jts/ibgateway/1042/  (número de versión varía)
```

### 4. Configurar API Settings

IB Gateway requiere configuración inicial con GUI. Opciones:

#### Opción A: VNC desde laptop (recomendado para primera vez)

```bash
# En VPS:
# Iniciar Xvfb en display :99
Xvfb :99 -screen 0 1024x768x16 &

# Iniciar VNC server
x11vnc -display :99 -bg -nopw -listen localhost -xkb

# Crear túnel SSH desde laptop:
ssh -L 5900:localhost:5900 root@100.75.4.17

# Conectar con VNC client desde laptop a localhost:5900
# macOS: Finder → Cmd+K → vnc://localhost:5900
# Windows: TightVNC, RealVNC, etc
```

Dentro del VNC:
1. Abrir terminal
2. Ejecutar: `DISPLAY=:99 /root/Jts/ibgateway/1042/ibgateway &`
3. Configurar:
   - **File → Global Configuration → API → Settings**
   - ✅ Enable ActiveX and Socket Clients
   - ✅ Allow connections from localhost
   - Socket port: **4002** (paper) o **4001** (live)
   - ✅ Read-Only API (inicial, para testing)
   - Trusted IPs: `127.0.0.1`
   - **Apply** → **OK**
4. Cerrar Gateway

#### Opción B: Editar config manualmente (avanzado)

```bash
# Config file (versión puede variar):
nano /root/Jts/ibgateway/1042/jts.ini

# Buscar y configurar:
[API]
port=4002
trusted-IPs=127.0.0.1
socket-client=1
readonly-api=0
```

---

## 🚀 Ejecutar Gateway en Headless

### Método 1: Script con Xvfb (recomendado)

Crear `/root/start_ibgateway.sh`:

```bash
#!/usr/bin/env bash
# Start IB Gateway in headless mode with Xvfb

DISPLAY=:99
GATEWAY_PATH="/root/Jts/ibgateway/1042"

# Matar procesos anteriores
pkill -f "Xvfb.*:99" || true
pkill -f "ibgateway" || true

# Iniciar Xvfb en background
Xvfb :99 -screen 0 1024x768x16 -ac &
sleep 2

# Iniciar Gateway
export DISPLAY=:99
cd "$GATEWAY_PATH"
./ibgateway &

# Esperar 10s para que inicie
sleep 10

# Verificar que puerto está en LISTEN
netstat -an | grep -E ":(4001|4002).*LISTEN"

echo "IB Gateway iniciado en display :99"
echo "Verificar logs en: $GATEWAY_PATH/logs/"
```

Hacer ejecutable y correr:

```bash
chmod +x /root/start_ibgateway.sh
/root/start_ibgateway.sh
```

### Método 2: PM2 (mantiene Gateway corriendo)

```bash
# Instalar PM2 (si no está)
npm install -g pm2

# Crear ecosystem file
cat > /root/ecosystem.config.js << 'EOF'
module.exports = {
  apps: [{
    name: 'IBKR-Gateway',
    script: '/root/start_ibgateway.sh',
    autorestart: true,
    restart_delay: 5000,
    max_restarts: 10,
  }]
};
EOF

# Iniciar con PM2
pm2 start /root/ecosystem.config.js
pm2 save

# Verificar
pm2 status
pm2 logs IBKR-Gateway
```

---

## ✅ Verificación

### 1. Verificar Gateway está corriendo

```bash
# Verificar proceso
ps aux | grep ibgateway

# Verificar puerto en LISTEN
netstat -an | grep -E ":(4001|4002).*LISTEN"
# Debería mostrar:
# tcp  0  0  127.0.0.1:4002  0.0.0.0:*  LISTEN

# O con ss:
ss -tulpn | grep -E ":(4001|4002)"
```

### 2. Test de conexión Python

```bash
cd /root/duckclaw
uv run python << 'EOF'
import asyncio
from duckclaw.ibkr_bracket_orders import connect_ibkr

async def test():
    try:
        ib = await connect_ibkr(host="127.0.0.1", port=4002, client_id=1)
        print("✅ Conexión IBKR Gateway OK")
        print(f"   Host: {ib.client.host}")
        print(f"   Port: {ib.client.port}")
        await ib.disconnect()
    except Exception as e:
        print(f"❌ Error: {e}")

asyncio.run(test())
EOF
```

Salida esperada:
```
✅ Conexión IBKR Gateway OK
   Host: 127.0.0.1
   Port: 4002
```

---

## 🔄 Auto-start en Boot

### Opción A: Systemd Service

Crear `/etc/systemd/system/ibgateway.service`:

```ini
[Unit]
Description=IB Gateway (Headless)
After=network.target

[Service]
Type=forking
User=root
WorkingDirectory=/root/Jts/ibgateway/1042
Environment="DISPLAY=:99"
ExecStartPre=/usr/bin/Xvfb :99 -screen 0 1024x768x16 -ac
ExecStart=/root/start_ibgateway.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Habilitar y iniciar:

```bash
sudo systemctl daemon-reload
sudo systemctl enable ibgateway
sudo systemctl start ibgateway

# Verificar
sudo systemctl status ibgateway
```

### Opción B: PM2 Startup

```bash
pm2 startup
# Seguir las instrucciones que muestra

pm2 save
```

---

## 🐛 Troubleshooting

### Gateway no inicia

**Síntoma**: `ps aux | grep ibgateway` no muestra proceso

**Solución**:
```bash
# Ver logs de Gateway
cat /root/Jts/ibgateway/1042/logs/*.log

# Ver si Xvfb está corriendo
ps aux | grep Xvfb

# Reiniciar Xvfb
pkill -f "Xvfb.*:99"
Xvfb :99 -screen 0 1024x768x16 -ac &
```

---

### Puerto no está en LISTEN

**Síntoma**: `netstat -an | grep 4002` no muestra nada

**Solución**:
```bash
# 1. Verificar que Gateway está corriendo
ps aux | grep ibgateway

# 2. Verificar config API en jts.ini
cat /root/Jts/ibgateway/1042/jts.ini | grep -A 5 "\[API\]"

# 3. Verificar logs
tail -f /root/Jts/ibgateway/1042/logs/*.log

# 4. Reiniciar Gateway
pkill -f ibgateway
/root/start_ibgateway.sh
```

---

### Connection refused desde Python

**Síntoma**: `ConnectionError: No se pudo conectar a IBKR Gateway`

**Solución**:
```bash
# 1. Verificar puerto correcto (.env)
cd /root/duckclaw
grep IBKR_PORT .env
# Debería mostrar: IBKR_PORT=4002 (paper) o 4001 (live)

# 2. Verificar firewall local (no debería bloquear localhost)
sudo iptables -L -n | grep 4002

# 3. Test directo con telnet
telnet 127.0.0.1 4002
# Si conecta: OK
# Si no: Gateway no está escuchando en ese puerto
```

---

### Gateway se cierra solo

**Síntoma**: Gateway inicia pero se cierra después de unos minutos

**Causa común**: Credenciales IBKR incorrectas o sesión expirada

**Solución**:
```bash
# Ver logs detallados
tail -f /root/Jts/ibgateway/1042/logs/*.log

# Si pide credenciales interactivas:
# 1. Detener Gateway
pkill -f ibgateway

# 2. Configurar autologin en jts.ini (NO recomendado para live)
nano /root/Jts/ibgateway/1042/jts.ini

# Agregar bajo [IBGateway]:
[IBGateway]
Username=tu_username_paper
Password=tu_password_encriptado
Trading=paper

# 3. Reiniciar
/root/start_ibgateway.sh
```

**Nota**: Para cuentas live, usar autenticación 2FA con TWS API (más seguro).

---

## 📊 Monitoring

### Logs importantes

```bash
# Gateway logs
tail -f /root/Jts/ibgateway/1042/logs/*.log

# Order Monitor logs (cron job)
tail -f /var/log/ibkr_order_monitor.log

# PM2 logs (si usas PM2)
pm2 logs IBKR-Gateway
```

### Health check script

Crear `/root/check_ibgateway.sh`:

```bash
#!/usr/bin/env bash
# Health check para IBKR Gateway

PORT=4002

# Check proceso
if ! pgrep -f "ibgateway" > /dev/null; then
    echo "❌ Gateway NO está corriendo"
    exit 1
fi

# Check puerto
if ! netstat -an | grep -E ":$PORT.*LISTEN" > /dev/null; then
    echo "❌ Puerto $PORT NO está en LISTEN"
    exit 1
fi

echo "✅ Gateway OK (puerto $PORT en LISTEN)"
exit 0
```

Agregar a cron (cada 5 min):

```bash
chmod +x /root/check_ibgateway.sh

# Agregar a crontab
(crontab -l 2>/dev/null; echo "*/5 * * * * /root/check_ibgateway.sh >> /var/log/ibgateway_health.log 2>&1") | crontab -
```

---

## 🔒 Seguridad

### Read-Only API (recomendado para testing)

En `jts.ini`:
```ini
[API]
readonly-api=1  # Solo lectura, no ejecuta órdenes
```

### Restricción por IP

Solo permitir localhost:
```ini
[API]
trusted-IPs=127.0.0.1
```

### Paper Trading vs Live

```bash
# Paper (testing):
IBKR_PORT=4002

# Live (real money):
IBKR_PORT=4001
```

**⚠️ IMPORTANTE**: Siempre testear primero en paper account antes de usar live.

---

## 📚 Referencias

- [IB Gateway User Guide](https://www.interactivebrokers.com/en/index.php?f=16457)
- [TWS API Configuration](https://interactivebrokers.github.io/tws-api/initial_setup.html)
- [ib_insync Documentation](https://ib-insync.readthedocs.io/)

---

**Status**: ✅ Documentación completa para setup headless en VPS Linux
