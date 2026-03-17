# Multi-Channel Broadcasting (The Mind Engine)

## 1. Objetivo Arquitectónico
Desacoplar el concepto de "Sesión de Juego" del "Chat de Telegram". El `TheMindCrupier` mantendrá el estado global de la partida en DuckDB, pero utilizará el `n8n_bridge` para emitir mensajes (Broadcast) a múltiples `chat_id` simultáneamente (mensajes públicos del crupier) o mensajes dirigidos (cartas privadas), todo desde una única ejecución del grafo.

## 2. Modelo de Datos Evolucionado (DuckDB)

El `chat_id` ya no es la clave primaria del juego. Introducimos el `game_id`.

```sql
CREATE TABLE the_mind_games (
    game_id VARCHAR PRIMARY KEY, -- Ej: "game_1234"
    status VARCHAR, -- 'waiting', 'playing', 'won', 'lost'
    current_level INTEGER DEFAULT 1,
    lives INTEGER,
    shurikens INTEGER,
    cards_played INTEGER[]
);

CREATE TABLE the_mind_players (
    game_id VARCHAR REFERENCES the_mind_games(game_id),
    chat_id VARCHAR, -- El DM de Telegram del jugador
    username VARCHAR,
    cards INTEGER[], -- La mano actual del jugador
    is_ready BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (game_id, chat_id)
);
```

## 3. Especificación de Skill: `BroadcastMessage`

El agente necesita una herramienta para hablar con todos los jugadores a la vez.

*   **Ubicación:** `packages/agents/src/duckclaw/forge/skills/broadcast.py`
*   **Contrato (Python):**
    ```python
    @tool
    def broadcast_message(game_id: str, message: str) -> str:
        """
        Envía un mensaje público a todos los jugadores de la partida.
        Úsalo para anunciar el inicio del nivel, errores o victorias.
        """
        # 1. Consultar DuckDB para obtener todos los chat_id del game_id
        # 2. Iterar y llamar a n8n_bridge.send_telegram_message(chat_id, message)
        # 3. Retornar "Broadcast exitoso"
    ```

## 4. Especificación de Skill: `DealCards` (Reparto Privado)

Esta es la herramienta crítica que envía payloads diferentes a cada jugador.

*   **Contrato (Python):**
    ```python
    @tool
    def deal_cards(game_id: str, level: int) -> str:
        """
        Reparte cartas a los jugadores según el nivel actual y se las envía por mensaje privado.
        """
        # 1. Generar N cartas aleatorias (1-100) por jugador (N = level)
        # 2. Actualizar la tabla the_mind_players con las nuevas manos
        # 3. Para cada jugador:
        #    n8n_bridge.send_telegram_message(chat_id, f"Tus cartas para el Nivel {level} son: {mano}")
        # 4. Retornar "Cartas repartidas en secreto."
    ```

## 5. El Flujo de Juego (User Journey)

1.  **Creación:** El Jugador 1 envía `/new_game the_mind`. El agente crea `game_1234` y responde: *"Partida creada. Dile a tus amigos que me envíen `/join game_1234`"*.
2.  **Unión:** El Jugador 2 envía `/join game_1234` por DM al bot.
3.  **Inicio:** El Jugador 1 envía `/start_game`.
    *   El agente usa `broadcast_message` -> *"¡Comienza el Nivel 1! Concéntrense..."* (Llega a ambos DMs).
    *   El agente usa `deal_cards` -> Jugador 1 recibe *"Tus cartas: [45]"*. Jugador 2 recibe *"Tus cartas:[12]"*.
4.  **Jugada:** El Jugador 2 envía `/play 12`.
    *   El agente valida en DuckDB. Es correcto.
    *   El agente usa `broadcast_message` -> *"✅ @Jugador2 jugó el 12."* (Llega a ambos DMs).

## 6. Integración con n8n (El Enrutador de Salida)

Para que esto funcione, n8n debe tener un flujo dedicado a **enviar mensajes**, no solo a recibirlos.

*   **Webhook (Trigger):** `POST /webhook/send-telegram`
*   **Payload Esperado:** `{"chat_id": "123456789", "text": "Mensaje del Crupier"}`
*   **Nodo Telegram:** Configurado con la operación `Send Message`, usando el `chat_id` y `text` del payload.