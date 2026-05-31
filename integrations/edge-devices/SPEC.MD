# DuckClaw Edge Link (DEL) — protocolo entre edge devices

Comunicación **agnóstica al hardware** entre dos (o más) hosts edge (portátiles, VPS, sensores serie) usando el mismo payload binario que `libedgecore` en serial.

## Capas

| Capa | Formato |
|------|---------|
| Transporte | TCP (puerto por defecto **9870**) |
| Envelope | `DEDG` + version + tipo + longitud + payload |
| Telemetría | Frame serial **51 bytes** (0xAA … 0xFF) + metadata `timestamp_ms` + `status_code` |

## Mensajes (envelope)

| Tipo | Valor | Payload |
|------|-------|---------|
| HELLO | 1 | `device_id` UTF-8, 16 bytes (handshake) |
| TELEMETRY | 2 | 51 B frame serial + 12 B (`int64` ts, `int32` status) |
| PING | 3 | vacío |
| PONG | 4 | vacío |

## Frame serial (51 bytes) — igual que `edge_core.cpp`

```
[0]     0xAA sync
[1-16]  device_id
[17-48] 8 × float32 LE
[49]    XOR(bytes 1..48)
[50]    0xFF footer
```

## CLI

```bash
# Portátil A
uv run python -m duckclaw_edge_devices.link --device-id LAPTOP-A --listen 0.0.0.0:9870 --stream

# Portátil B (misma LAN o Tailscale)
uv run python -m duckclaw_edge_devices.link --device-id LAPTOP-B --connect LAPTOP-A:9870 --stream
```

Variables: `DUCKCLAW_EDGE_DEVICE_ID`, `DUCKCLAW_EDGE_LIB_PATH`.
