# CRM: resumen ejecutivo GovTech vía DuckClaw Gateway

## Objetivo

El panel **«Análisis de IA GovTech»** en el detalle de ticket (`TicketDetail`) muestra un **resumen ejecutivo** generado por inferencia contra el mismo **API Gateway** DuckClaw que el módulo «Generar con IA» (worker `PQRSD-Assistant`, tenant `PQRS`), en lugar de depender solo del texto estático en `mockData`.

## Alcance (implementación)

- **Next.js (CRM en `external/retoPWRSomegahack/`)**
  - [`src/lib/duckclaw-gateway.ts`](../../../external/retoPWRSomegahack/src/lib/duckclaw-gateway.ts): URL del gateway, `postPqrsAssistantChat`, `crmGatewayUserId`, parseo de `response`.
  - `POST /api/ia/resumen-ejecutivo`: mensaje de sistema acotado a resumen corto (2–4 frases), `chat_id` `crm-resumen-{idTicket}` para no mezclar historial con `crm-ticket-{id}` del borrador oficial.
  - `POST /api/ia/regenerar` (co-pilot «Generar con IA»): valida `instruccionFuncionario` en servidor ([`validate-instruccion-funcionario.ts`](../../../external/retoPWRSomegahack/src/lib/ia/validate-instruccion-funcionario.ts)) antes del gateway. Si detecta instrucciones de sistema/comandos (p. ej. `sudo`, `curl`) o texto con muy poca proporción de letras, responde **200** con `invalid_request: true`, `text` institucional y **sin** invocar al LLM; el cliente no aplica ese texto al editor oficial.
  - `useTicketDetail`: tras cargar el ticket, si `NEXT_PUBLIC_IA_HABILITADA=true`, llama al endpoint con `AbortController`; fusiona `resumenIa` en estado; errores en `resumenError` con degradación si había mock.
  - `TicketDetail`: estados de carga y error en la sección de análisis.

## Variables de entorno

Mismas que el proxy de redacción: `DUCKCLAW_GATEWAY_URL` (o `NEXT_PUBLIC_*`), `NEXT_PUBLIC_IA_HABILITADA`, opcional `DUCKCLAW_GATEWAY_USER_ID_OVERRIDE` para desarrollo.

## Comportamiento ante fallo

- Si el gateway falla y el ticket tenía `resumenIa` en mock: se muestra el mock y aviso ámbar.
- Si falla y no había resumen: caja de error roja con el mensaje.

## Fuera de alcance (futuro)

- Persistir `resumen_ia` en DuckDB desde el CRM (los **tickets** y respuestas oficiales sí: ver [CRM PQRSD persistencia DuckDB.md](CRM%20PQRSD%20persistencia%20DuckDB.md)).
- Endpoint dedicado de solo-resumen en el gateway (menor latencia/coste).
- Caché por `idTicket` (p. ej. `sessionStorage`) para no repetir llamada al reabrir.
