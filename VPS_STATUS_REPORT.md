# 📊 Reporte de Estado VPS Producción - Capadonna Driller

**Fecha:** 11 Sep 2026, 03:54 UTC  
**VPS:** ubuntu-2gb-ash-1 (100.75.4.17)  
**Uptime:** 1h 4m  
**Conexión:** ✅ Establecida vía Tailscale + SSH

---

## 🖥️ Recursos del Sistema

### Memoria (⚠️ CRÍTICO)
```
Total:      1.9GB
Usada:      1.2GB (63%)
Libre:      393MB (20%)
Swap:       2.0GB (232MB en uso)
```
**Estado:** Solo 393MB libres - **requiere atención**

### Disco (🔴 CRÍTICO)
```
Total:      38GB
Usado:      33GB (91%)
Libre:      3.3GB
```
**Estado:** **91% de uso** - requiere limpieza o upgrade urgente

---

## 📦 Procesos PM2 (5 Online, 3 Stopped)

### ✅ Online:
| Proceso | RAM | Uptime | Status |
|---------|-----|--------|--------|
| DuckClaw-Gateway | 142.5MB | 64m | 🟢 online |
| DuckClaw-DB-Writer | 166.6MB | 64m | 🟢 online |
| DuckClaw-Heartbeat | 125.3MB | 64m | 🟢 online |
| duckclaw-admin-ui | 64.1MB | 64m | 🟢 online |
| Android-MCP | 2.4MB | 64m | 🟢 online |

### ⏸️ Stopped:
- quant-hrp-weekly
- quant-market-regime-spy  
- quant-portfolio-sync

---

## 💾 Uso de Disco Detallado

### Capadonna-Driller (/root/Capadonna-Driller)
```
13GB    - db/ (DuckDB databases)
  ├─ 7.4GB  duckclaw.duckdb (principal)
  └─ 4.8GB  private/ (vaults)
163MB   - conversation_traces
80MB    - results
72MB    - capadonna_driller_venv_windows
19MB    - state
13MB    - scripts
```

**Total: ~13.4GB solo en este proyecto**

---

## 📁 Repositorios Encontrados

### 1. `/root/Capadonna-Driller/` (Trading - Activo)
**Git Status:**
- ✏️ 12 archivos modificados (quant trading logic)
- 📄 Archivos nuevos sin track:
  - `dashboard_quant_trader_c480f0c7.html` (5.4KB)
  - Scripts de deployment

**Últimos Commits:**
```
46aa769 fix(ibkr): require live portfolio marks
3e78390 fix(quant): version PM2 COT schedules
bb08c43 fix(ibkr): request historical bars in UTC
3132c56 fix(market): fall back to IBKR after lake
fc7b07b fix(quant): orchestrate dashboard HTML via invoke_worker
```

### 2. `/root/duckclaw/` (Framework Base)
- Contiene el `.env` principal
- Framework genérico DuckClaw

---

## 🎯 Dashboard HTML

### Archivo Encontrado:
`/root/Capadonna-Driller/dashboard_quant_trader_c480f0c7.html`

**Características:**
- Diseño moderno dark theme
- Responsive (mobile-friendly)
- Componentes: métricas, gráficos, tablas
- 5.4KB de tamaño

**Estado según Notion:** "In Progress" - equity, régimen, IBKR sync

---

## ⚠️ Problemas Críticos Detectados

### 1. Espacio en Disco (🔴 Urgente)
- **91% usado** - solo 3.3GB libres
- **13GB en db/** - crece constantemente
- **Riesgo:** Falla del sistema si llega a 100%

**Soluciones:**
- [ ] Limpiar conversation_traces antiguos (163MB)
- [ ] Archivar o comprimir resultados viejos (80MB)
- [ ] Evaluar vacuum de DuckDB (7.4GB puede tener espacio recuperable)
- [ ] **Upgrade a VPS de 4GB RAM + 80GB disco** (recomendado)

### 2. Memoria Limitada (⚠️ Alta)
- **Solo 393MB libres** con 1.9GB total
- **Swap en uso** (232MB) - indica presión de memoria
- **Build de Next.js falla** con OOM (según `build_admin_vps.sh`)

**Impacto:**
- Procesos pueden ser killed por OOM
- Performance degradado
- Builds requieren stop de otros procesos

**Solución:**
- [ ] Upgrade a 4GB RAM (Contabo ~€7/mes evaluado según AJUSTES_VPS.md)

### 3. Procesos Quant Stopped
- quant-hrp-weekly
- quant-market-regime-spy
- quant-portfolio-sync

**Acción:** Verificar si deben estar corriendo o son cron jobs.

---

## ✅ Aspectos Positivos

1. **Gateway Health:** ✅ OK (endpoint `/health` responde)
2. **DB Writer Queue:** 0 items (sin backlog)
3. **Procesos principales:** Todos online y estables (64m uptime)
4. **Tailscale:** Conectado y funcionando
5. **PM2:** Configurado y operativo

---

## 📋 Tareas Pendientes (según Notion)

### 🔄 En Progreso
- **Dashboard HTML** (equity, régimen, IBKR sync)
  - Archivo existe: `dashboard_quant_trader_c480f0c7.html`
  - Último commit menciona: "orchestrate dashboard HTML via invoke_worker"

### ⏳ Pendientes Alta Prioridad
1. ⚠️ **Escalar VPS 2GB → 4GB** (crítico por memoria y disco)
2. MAE/MFE tracking en evaluate_cfd_state
3. Evaluar migración LLM (Haiku 4.5 + MLX local)

### ⏳ Pendientes Media Prioridad
4. Deflated Sharpe Ratio (DSR) en v_session_performance
5. IB Gateway paper sin mark-to-market (8 posiciones)
6. LIN/PTRN/MRVL — watchlist perdida

---

## 🚀 Plan de Acción Inmediato

### Hoy (Urgente):
1. [ ] Liberar espacio en disco:
   ```bash
   # Limpiar logs viejos
   pm2 flush
   
   # Archivar conversation_traces antiguos
   cd /root/Capadonna-Driller
   tar -czf conversation_traces_backup_$(date +%Y%m%d).tar.gz conversation_traces/
   # (luego mover a otro servidor o eliminar los antiguos)
   ```

2. [ ] Verificar integridad de DuckDB y considerar vacuum:
   ```bash
   # Verificar tamaño recuperable
   sqlite3 db/duckclaw.duckdb "VACUUM;"
   ```

3. [ ] Revisar y completar Dashboard HTML (tarea en progreso)

### Esta Semana (Alta):
4. [ ] Evaluar proveedores para upgrade VPS:
   - Contabo: 4GB RAM, 80GB NVMe (~€7/mes)
   - Hetzner: CPX21 (3 vCPU, 4GB RAM, 80GB) (~€6.90/mes)

5. [ ] Planificar migración sin downtime

### Medio Plazo:
6. [ ] Implementar MAE/MFE tracking
7. [ ] Evaluar migración LLM (Haiku 4.5)

---

## 📝 Notas Técnicas

- **DuckDB:** Modelo DB-first, solo DB-Writer escribe (ACID)
- **PM2:** Stack completo desplegado (Gateway, DB-Writer, Heartbeat, Admin)
- **Framework:** DuckClaw (open source) + Capadonna-Driller (privado trading)
- **Arquitectura:** Multi-agente con manager/workers pattern
- **Inspiración:** TauricResearch/TradingAgents (99.8K ⭐)

---

## 🔗 Referencias
- AJUSTES_VPS.md
- CLAUDE.md (guía de desarrollo)
- docs/architecture/AGENT_HARNESS_CONTROL.md
- Notion: Capadonna Driller Tasks

---

**Generado por:** cursor-cloud-agent-8853  
**Conexión VPS:** ✅ Activa vía Tailscale (100.102.83.98 → 100.75.4.17)
