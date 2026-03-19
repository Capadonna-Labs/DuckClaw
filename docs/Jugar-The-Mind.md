# Cómo jugar The Mind con DuckClaw

Guía para jugar **The Mind** en un grupo de Telegram usando el crupier virtual **TheMindCrupier** de DuckClaw.

---

## 1. Qué es The Mind

The Mind es un juego de cartas cooperativo. Los jugadores tienen cartas numeradas (1–100) y deben jugarlas **en orden ascendente** sin poder hablar de los números. Si alguien juega una carta y otro tenía una menor sin jugarla, pierden una vida. El objetivo es superar todos los niveles sin quedarse sin vidas.

---

## 2. Configuración en el grupo

1. **Añadir el crupier al equipo del chat**  
   En el grupo donde quieres jugar, escribe:
   ```
   /workers --add TheMindCrupier
   ```
   (También vale `themindcrupier` en minúsculas.)

2. **Comprobar**  
   Con `/workers` verás que TheMindCrupier está en el equipo. Con `/roles` puedes ver que el template está disponible.

3. **Requisitos**  
   - El bot debe poder enviar **mensajes directos (DM)** a cada jugador para repartir las cartas en secreto.  
   - El webhook de n8n (o el canal que use el gateway) debe estar configurado para enviar `chat_id`, `user_id` y `username` en cada mensaje, así el crupier sabe quién juega y puede enviar DMs.

---

## 3. Comandos del juego

El flujo nuevo separa la **creación de la partida** (con `game_id`) del chat concreto donde escribes.

| Comando | Dónde | Descripción |
|--------|-------|-------------|
| **/start_mind** | Cualquier chat | Inicializa el esquema de tablas de The Mind en DuckDB (una sola vez). |
| **/new_game the_mind** | Chat del creador (DM o grupo) | Crea una partida nueva de The Mind y devuelve un `game_id` (ej. `game_1234_aaaa`). |
| **/join \<game_id\>** | DM de cada jugador | El jugador se apunta a esa partida; el bot asocia su `chat_id` de DM al `game_id`. |
| **/start_game \[game_id\]** | Chat del creador | Pone la partida en estado `playing` y deja listo el nivel 1. Si no indicas `game_id`, toma la última partida en `waiting`. |
| **/play \<número\>** | DM de cada jugador | Registra que juegas esa carta en tu partida activa. Ejemplo: `/play 15`. El motor comprueba que tengas la carta, que nadie tuviera una menor, y actualiza vidas y estado. |

---

## 4. Flujo de una partida

1. **Inicializar esquema (una vez)**  
   Escribe `/start_mind` en cualquier chat donde tengas al bot. Si ya existe el esquema, no pasa nada.

2. **Crear la partida**  
   El jugador que actuará como organizador escribe en su chat (DM o grupo):  
   `/new_game the_mind`  
   El bot responde con un `game_id`, por ejemplo: `game_1731000000_abcd`.

3. **Unirse a la partida**  
   Cada jugador abre un **DM** con el bot y escribe:  
   `/join game_1731000000_abcd`  
   Así el motor asocia su `chat_id` privado a esa partida.

4. **Empezar a jugar**  
   El organizador escribe:  
   `/start_game game_1731000000_abcd`  
   (o simplemente `/start_game` si solo hay una partida en `waiting`).

5. **Repartir cartas (vía herramienta `deal_cards`)**  
   El crupier (LLM) usará la herramienta `deal_cards(game_id, level)` para repartir cartas por DM cuando toque empezar un nivel. Cada jugador recibirá un mensaje tipo:  
   `Tus cartas para el Nivel 1 son: [12, 45, 78]`.

6. **Jugar cartas**  
   Los jugadores, **sin decir sus números en voz alta**, van enviando desde su DM:  
   - `/play 12`  
   - `/play 45`  
   - …  
   El motor valida cada jugada y actualiza las tablas (`the_mind_games` y `the_mind_players`).

7. **Mensajes a todos (broadcast)**  
   El crupier usará la herramienta `broadcast_message(game_id, message)` para avisar a todos los jugadores a la vez (por ejemplo: *\"✅ @Jugador2 jugó el 12\"*, *\"❌ Error, pierden una vida\"*, *\"Nivel superado\"*).

---

## 5. Reglas que aplica el motor

- **Orden:** Solo se puede jugar una carta si nadie tiene una carta con número menor sin jugar. Si alguien juega (por ejemplo) el 15 y otro jugador tenía una carta &lt; 15, **pierden una vida** y se eliminan esas cartas menores de todas las manos.
- **Cartas en secreto:** Las cartas se reciben solo por DM. No se deben escribir los números en el chat del grupo (solo el comando `/play <numero>` cuando toca jugar).
- **Vidas y shurikens:** El número de vidas y el uso de shurikens lo gestiona el motor según el nivel (ver especificación del juego en el repo).

---

## 6. Resumen rápido

```
/workers --add TheMindCrupier    → Añadir crupier al equipo
/start_mind                       → Inicializar esquema de The Mind
/new_game the_mind                → Crear partida y obtener game_id
/join <game_id>                   → Unirse a la partida desde tu DM
/start_game [game_id]             → Poner la partida a jugar
/play 15                          → Jugar la carta 15 (en tu DM)
```

Para más detalle técnico (tablas DuckDB, fly commands, skills `send_dm`, `broadcast_message`, `deal_cards`), ver las specs:  
`specs/features/Multi-Threading, Gestión de Grupos y Motor de Juegos (The Mind).md` y  
`specs/features/Multi-Channel Broadcasting (The Mind Engine).md`.
