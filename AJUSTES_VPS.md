# Ajustes Pendientes VPS Producción

**Fecha:** 11 Sep 2026  
**VPS:** 100.75.4.17 (Tailscale)  
**RAM:** 2GB (pendiente escalar a 4GB)

## 🔍 Diagnóstico

Ejecutar en el VPS:

```bash
cd ~/duckclaw  # o donde esté el repo
bash scripts/vps_diagnostic.sh > diagnostic_$(date +%Y%m%d_%H%M%S).log
```

## 📋 Tareas Pendientes (según Notion)

### 🔄 En Progreso

1. **Mejora de Dashboard HTML — datos reales**
   - Estado: In Progress
   - Componentes: equity, régimen, IBKR sync
   - Archivos probables:
     - `packages/shared/src/duckclaw/position_metrics.py`
     - Custom reports bridge
     - Admin dashboard components

### ⏳ Pendientes Alta Prioridad

2. **Escalar VPS 2GB → 4GB**
   - **Razón:** `ML_models/`, `results/`, `conversation_traces/`, `db/` ~15GB y creciendo
   - **Impacto:** Build de Next.js falla con OOM en 2GB (ver `scripts/build_admin_vps.sh`)
   - **Mitigación actual:** 
     ```bash
     # build_admin_vps.sh stopea procesos durante build
     pm2 stop DuckClaw-Gateway DuckClaw-DB-Writer
     export NODE_OPTIONS="--max-old-space-size=1536"
     ```
   - **Acción:** Evaluar Contabo u otro proveedor

3. **MAE/MFE tracking en evaluate_cfd_state**
   - Research MQL5
   - Estado: Not started
   - Ubicación probable: position metrics / trading logic

### ⏳ Pendientes Media Prioridad

4. **Evaluar migración LLM**
   - Haiku 4.5 (más eficiente)
   - Plan SLM local MLX (Mac Mini)
   - Estado: Not started

5. **Deflated Sharpe Ratio (DSR) en v_session_performance**
   - Métrica de trading más robusta
   - Estado: Not started

6. **IB Gateway paper sin mark-to-market**
   - 8 posiciones pendientes
   - Estado: Not started

7. **LIN/PTRN/MRVL — watchlist perdida**
   - Decisión: recuperar o descartar
   - Estado: Not started

## 🛠️ Ajustes Técnicos Detectados

### Ponytail Comments (Corner-cuts con upgrade path)

```python
# packages/shared/src/duckclaw/admin_mcp_connectors.py:415
# ponytail: workspacemcp search_corpus fails TaskGroup on VPS; 
# Gmail REST covers email.
```

Verificar si este issue persiste en VPS actual.

### Tool Harness & Packs

El sistema implementa:
- Progressive disclosure (Claude)
- Approval modes (Codex)
- Circuit breakers
- Runtime tool packs

**Estado:** Fase 1 completa, Fase 2 pendiente (HITL real para destructive operations)

## 🚀 Scripts de Deployment Disponibles

```bash
# Deploy notification fix
bash scripts/deploy_notification_fix_vps.sh

# Deploy Android vision + MCP pool
bash scripts/deploy_android_vision_vps.sh

# Build admin (low-memory)
bash scripts/build_admin_vps.sh
```

## 📊 Métricas a Revisar

1. **PM2 Health:**
   ```bash
   pm2 status
   pm2 monit
   ```

2. **Memory Usage:**
   ```bash
   free -h
   du -sh ML_models/ results/ conversation_traces/ db/
   ```

3. **Gateway Health:**
   ```bash
   curl http://localhost:8000/health | jq '.'
   ```

4. **DB Writer Queue:**
   ```bash
   redis-cli LLEN duckdb_write_queue
   ```

## ⚠️ Gaps Conocidos (desde arquitectura docs)

| Pri | Gap |
|-----|-----|
| P0 | Exponer `tools_bound` / `harness_metric` en admin Overview |
| P1 | ArgsSchema / Field descriptions homogéneos |
| P1 | Envelope en **todos** los bridges |
| P1 | HITL real `PENDING_HITL` para destructive |
| P2 | Verify-loop post-sandbox |
| P3 | Provider Tool Search nativo |

## 🎯 Próximos Pasos Sugeridos

1. **Inmediato:**
   - Ejecutar `vps_diagnostic.sh`
   - Revisar logs de PM2
   - Verificar espacio en disco

2. **Corto plazo:**
   - Continuar Dashboard HTML (equity, régimen, IBKR sync)
   - Evaluar upgrade VPS a 4GB

3. **Medio plazo:**
   - MAE/MFE tracking
   - Migración LLM más eficiente
   - DSR metric

## 📝 Notas

- **No forzar commits** sin revisar
- **No force push** a menos que sea explícitamente solicitado
- **Git branches:** usar `cursor/<descriptive-name>-8853` format
- **Commit messages:** descriptivos, por cambio lógico
