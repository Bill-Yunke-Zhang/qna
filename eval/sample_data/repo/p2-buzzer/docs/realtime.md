# How Real-Time Works in Buzzer

Lecture covered REST: the client sends a request, the server sends one response, the connection is done. A live quiz game can't work that way — when the host advances to the next question, the server must push that fact to every player *immediately*, without any player asking for it. Buzzer does this with **Socket.io** (WebSockets): each browser holds one persistent, two-way connection to the backend for the duration of a game.

This document traces **one player answering one question**, end to end, so you can see every moving part. Read it before you modify anything in the game loop — new question types, scoring changes, and host-screen features all flow through this path.

## The cast

| Piece | Where it lives | Role |
|---|---|---|
| Event name constants | `backend/app/websocket/events.py` | The complete vocabulary — every event the client and server can send. Start here. |
| Gateway | `backend/app/websocket/gateway.py` | The server-side handlers: one `@sio.on(...)` function per client→server event. |
| JWT middleware | `backend/app/websocket/middleware.py` | Authenticates the socket connection using the same JWT you get from `/api/auth/login`. |
| State service | `backend/app/services/state_service.py` | Live game state in **Redis** (current question, who has answered, scores) — fast, per-room, expires with the room. |
| Game service | `backend/app/services/game_service.py` | Scoring logic (`record_answer` and the per-type scoring branches) and **MySQL** persistence — every answer is written to the database immediately. |
| Player client | `frontend/player/src/pages/game/GameLayout.tsx` | Opens the socket, listens for server events, sends answers. |

Note the division of labor: **Redis holds the ephemeral live state; MySQL holds the permanent record.** The gateway orchestrates both on every answer.

## Trace: one answer, end to end

Assume the host has started a question, so every player has already received a `new_question` event (see payload shape in `_question_payload()` in the gateway — it deliberately includes `config` but **never** `answer_data`, so the correct answer is never in the browser).

**1. Player taps an option.** The player app emits one event over its existing socket:

```js
socket.emit("submit_answer", {
  question_id: 42,
  answer_data: { selectedIndex: 2 },   // shape depends on question type
  answer_time_ms: 4180,
});
```

`answer_data` is a type-specific dict: `{selectedIndex}` for multiple choice, `{selectedValue}` for true/false, `{text}` for fill-in-the-blank, `{selectedIndices}` for multi-select. If you add a question type, you are defining a new `answer_data` shape.

**2. The gateway validates before it scores** (`on_submit_answer` in `gateway.py`). In order, it checks: the sender is an authenticated PLAYER in a room; a question is actually open (`question_phase == "QUESTION"` in Redis) and not locked; the submitted `question_id` matches the live question; and the player hasn't already answered (idempotent — a duplicate gets an `answer_received` reply with `alreadyAnswered: true` and is *not* re-scored). Any failure emits an `error` event **to that player only**, and nothing is recorded.

**3. Scoring and persistence.** The gateway calls `game_service.record_answer(...)`, which dispatches on `question.type` to compute correctness and points, writes the answer to **MySQL**, and updates the player's running score in **Redis**.

**4. The server fans out three different notifications** — this is the part REST can't do:

- To **the answering player** only: `answer_received` — `{questionId, isCorrect, pointsAwarded, totalScore}`.
- To **the host screen** only: `answer_status` — `{userId, answeredCount, totalPlayers}` (this is how the host's live "12/30 answered" counter works).
- If that was the **last** unanswered player: `answer_phase_ended` to the host, and the server cancels the question countdown timer.

Meanwhile every player who *didn't* answer receives nothing — their screens change only when the host advances and the server broadcasts `question_results` and then the next `new_question` to the whole room.

## The full event vocabulary

Client → server: `join_room`, `rejoin_room`, `submit_answer`, and host-only `host_advance`, `host_lock_question`.
Server → client: room-wide broadcasts (`new_question`, `question_results`, `game_over`, `player_joined`, `player_left`, `question_locked`/`question_unlocked`, `host_disconnected`, `game_abandoned`), player-targeted replies (`answer_received`, `sync_state`, `error`), and host-only status (`answer_status`, `answer_phase_ended`).

All names are defined once in `events.py` and imported everywhere — if you add an event, add it there.

## Seeing it live

Two ways to watch this trace happen without hand-driving 30 browser tabs:

```bash
# Scripted end-to-end game that asserts on every event payload:
python scripts/smoke_test_websocket.py

# Fill a real room with simulated players (create a room in the Host app first):
python scripts/simulate_players.py --room <CODE>
```

Both scripts speak the socket protocol directly (no browser), so reading them is also the fastest way to learn the client side of the contract. The integration tests in `tests/integration/engine/socket_client.py` do the same thing under pytest.

## Rules of thumb when you extend the game loop

- **Server is the referee.** Never trust the client: validate the answer shape in the gateway (see the `multi_select` bounds-check for the pattern), score in `game_service`, and never send `answer_data` to the browser.
- **Redis for live state, MySQL for the record.** If it must survive the room ending, it goes in MySQL. If it's "what is happening right now," it goes through `state_service`.
- **Pick the right audience for every emit:** the room, the host room (`_host_room(...)`), or one `sid`. Broadcasting a player's score to the whole room is a bug; so is telling only one player the question changed.
