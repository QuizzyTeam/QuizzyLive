import json
import time
import uuid
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from pydantic import ValidationError
from app.core.redis_manager import get_redis
from app.ws.room_manager import RoomManager
from app.ws.schemas import (
    EventPayload,
    HostCreateSession,
    HostStartQuestion,
    HostRevealAnswer,
    HostNextQuestion,
    HostEndSession,
    PlayerJoin,
    PlayerAnswer,
    ServerStateSync,
    FinishedSessionSnapshot,
)
from app.services.quiz_session_service import QuizSessionService
from app.services.room_quiz_cache import (
    fetch_room_quiz,
    questions_to_runtime,
    delete_room_quiz,
)

ws_router = APIRouter()
manager = RoomManager()

async def send_error(websocket: WebSocket, message: str) -> None:
    await websocket.send_text(json.dumps({"type": "error", "message": message}))

@ws_router.websocket("/ws")
async def ws_endpoint(
    websocket: WebSocket,
    role: str = Query(regex="^(host|player)$"),
    roomCode: str = Query(...),
    name: str | None = None,
    playerId: str | None = Query(default=None),
) -> None:
    print("\n" + "=" * 60)
    print(f"Новий WebSocket запит: Role: {role}, RoomCode: {roomCode}, Name: {name}")
    print("=" * 60 + "\n")

    r = await get_redis()
    await manager.register(roomCode, websocket)

    player_id: str | None = None
    player_name: str | None = None
    session_key = f"session:{roomCode}"
    monitor_task = None

    try:
        if role == "player":
            print(f"Обробка підключення PLAYER: {name}")
            session_raw = await r.get(session_key)
            session_exists = session_raw is not None
            meta_exists = await r.exists(f"quiz:session_meta:{roomCode}")
            
            if not session_exists and not meta_exists:
                await send_error(websocket, "Вікторина не знайдена або ще не створена")
                await websocket.close()
                return

            if session_exists:
                session_data = json.loads(session_raw)
                if session_data.get("phase") == "ENDED":
                    await send_error(websocket, "Вікторина вже завершена")
                    await websocket.close()
                    return

            if playerId is not None:
                stored_name = await r.hget(manager.k_players(roomCode), playerId)
                if stored_name is not None:
                    player_id = playerId
                    player_name = stored_name
                    print(f"Відновлено гравця за playerId={player_id[:8]}")

            if player_id is None and name:
                all_players = await r.hgetall(manager.k_players(roomCode))
                for pid, pname in all_players.items():
                    if pname == name:
                        player_id = pid
                        player_name = pname
                        print(f"Відновлено гравця за ім'ям, player_id={player_id[:8]}")
                        break

            if player_id is None:
                player_id = str(uuid.uuid4())
                player_name = name or "Player"
                print(f"Створено нового player_id: {player_id[:8]}")

            await r.hset(manager.k_players(roomCode), mapping={player_id: player_name})
            await r.expire(manager.k_players(roomCode), 6 * 60 * 60)

            state = await manager.get_state(r, roomCode)
            questions = await manager.load_questions(r, roomCode)
            qidx = state.get("questionIndex", -1)
            question = questions[qidx] if 0 <= qidx < len(questions) else None
            sb = await manager.scoreboard(r, roomCode)

            ss = ServerStateSync(
                roomCode=roomCode,
                phase=state.get("phase", "LOBBY"),
                questionIndex=qidx,
                startedAt=state.get("startedAt"),
                durationMs=state.get("durationMs"),
                question=question,
                scoreboard=sb,
                reveal=None,
                playerId=player_id,
            )
            await websocket.send_text(ss.model_dump_json())

            # Завжди відправляємо player_joined broadcast, щоб хост міг оновити список
            # (навіть якщо гравець перезавантажує сторінку)
            await manager.broadcast(
                roomCode,
                {"type": "player_joined", "playerName": player_name, "playerId": player_id, "roomCode": roomCode},
                exclude=websocket,
            )

        elif role == "host":
            print(f"Обробка підключення HOST для кімнати: {roomCode}")
            # Якщо хост підключається - видаляємо ключ відсутності (якщо він був встановлений)
            # Це означає, що хост повернувся і таймер не повинен спрацювати
            # Видалення ключа також сигналізує monitor_host_disconnect, що хост повернувся
            await r.delete(manager.k_host_presence(roomCode))
            
            state = await manager.get_state(r, roomCode)
            questions = await manager.load_questions(r, roomCode)
            qidx = state.get("questionIndex", -1)
            question = questions[qidx] if 0 <= qidx < len(questions) else None
            sb = await manager.scoreboard(r, roomCode)

            ss = ServerStateSync(
                roomCode=roomCode,
                phase=state.get("phase", "LOBBY"),
                questionIndex=qidx,
                startedAt=state.get("startedAt"),
                durationMs=state.get("durationMs"),
                question=question,
                scoreboard=sb,
                reveal=None,
                playerId=None,
            )
            await websocket.send_text(ss.model_dump_json())

        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            event_type = data.get("type")
            print(f"\nОтримано подію: {event_type} від {role}")

            try:
                if event_type == "host:create_session":
                    evt = HostCreateSession(**data)
                    await handle_create_session(websocket, r, roomCode, evt, session_key)
                elif event_type == "host:start_question":
                    evt = HostStartQuestion(**data)
                    await handle_start_question(websocket, r, roomCode, evt)
                elif event_type == "host:next_question":
                    evt = HostNextQuestion(**data)
                    await handle_next_question(websocket, r, roomCode, evt)
                elif event_type == "host:reveal_answer":
                    evt = HostRevealAnswer(**data)
                    await handle_reveal_answer(websocket, r, roomCode, evt)
                elif event_type == "host:end_session":
                    evt = HostEndSession(**data)
                    await handle_end_session(websocket, r, roomCode, session_key)
                elif event_type == "player:join":
                    evt = PlayerJoin(**data)
                    await handle_player_join(websocket, r, roomCode, evt, player_id, player_name)
                elif event_type == "player:answer":
                    evt = PlayerAnswer(**data)
                    await handle_player_answer(websocket, r, roomCode, evt, player_id)
                else:
                    await send_error(websocket, f"Невідомий тип події: {event_type}")

            except ValidationError as e:
                print(f"Помилка валідації: {str(e)}")
                await send_error(websocket, f"Помилка валідації: {str(e)}")

    except WebSocketDisconnect:
        print(f"\nВідключення: {role} від {roomCode}")
        if role == "host":
            # Перевіряємо, чи ми в фазі LOBBY перед запуском моніторингу
            state = await manager.get_state(r, roomCode)
            if state.get("phase") == "LOBBY":
                # Встановлюємо ключ відсутності хоста (TTL 70 секунд для безпеки)
                await r.setex(manager.k_host_presence(roomCode), 70, "disconnected")
                # Запускаємо моніторинг - якщо хост не повернеться за 1 хвилину, викинемо гравців
                monitor_task = asyncio.create_task(monitor_host_disconnect(r, roomCode))
                print(f"[host_disconnect] Запущено моніторинг відсутності хоста для {roomCode}")
    except Exception as e:
        print(f"\nПомилка WebSocket: {str(e)}")
    finally:
        await manager.unregister(roomCode, websocket)
        if role == "host":
            # Якщо хост відключився в фазі LOBBY, моніторинг вже запущений
            # Якщо хост відключився в іншій фазі або під час помилки - просто видаляємо ключ
            state = await manager.get_state(r, roomCode)
            if state.get("phase") != "LOBBY":
                await r.delete(manager.k_host_presence(roomCode))
                if monitor_task:
                    monitor_task.cancel()

async def handle_create_session(
    websocket: WebSocket,
    r,
    roomCode: str,
    evt: HostCreateSession,
    session_key: str,
) -> None:
    """Створення сесії (ініціалізація в Redis)"""
    print("Створення сесії (WS handler)")
    
    quiz_id = evt.quizId
    questions = [q.model_dump() for q in evt.questions]
    quiz_title = None 

    # Спроба дістати дані з метаданих (які створив REST endpoint)
    meta_raw = await r.get(f"quiz:session_meta:{roomCode}")
    if meta_raw:
        meta = json.loads(meta_raw)
        if not quiz_id:
            quiz_id = meta.get("quizId")
        quiz_title = meta.get("quizTitle")

    # Якщо REST уже закешував повний квіз — використовуємо його
    cached_quiz = await fetch_room_quiz(r, roomCode)
    if cached_quiz:
        if not quiz_id:
            quiz_id = cached_quiz.get("id")
        if not quiz_title:
            quiz_title = cached_quiz.get("title")
        if not questions:
            questions = questions_to_runtime(cached_quiz)

    # Якщо питань немає (фронтенд надіслав пустий список) і кешу не було, вантажимо з БД
    if not questions and quiz_id:
        print("Завантаження питань та інфо з БД...")
        try:
            from app.services.quiz_service import QuizService
            from app.repositories.quiz_repository import QuizRepository
            from app.core.supabase_client import get_supabase
            
            repo = QuizRepository(get_supabase())
            svc = QuizService(repo)
            
            quiz_data = svc.get_quiz(quiz_id)
            if quiz_data:
                questions = questions_to_runtime(quiz_data)
                # Якщо title не було в метаданих, беремо з БД
                if not quiz_title:
                    quiz_title = quiz_data["title"]
                print(f"Завантажено {len(questions)} питань")
        except Exception as e:
            print(f"DB Error: {e}")
            await send_error(websocket, f"Помилка отримання питань: {str(e)}")
            return

    session_id = str(uuid.uuid4())
    created_at_ms = int(time.time() * 1000)

    session_data = {
        "sessionId": session_id,
        "roomCode": roomCode,
        "quizId": quiz_id,
        "quizTitle": quiz_title, # <--- ЗБЕРІГАЄМО TITLE
        "questions": questions,
        "phase": "LOBBY",
        "questionIndex": -1,
        "players": [],
        "createdAt": created_at_ms,
    }
    
    await r.set(session_key, json.dumps(session_data))
    print(f"Збережено {session_key} (Title: {quiz_title})")

    await manager.create_session(r, roomCode, questions, session_id, created_at_ms)

    state = await manager.get_state(r, roomCode)
    # Отримуємо актуальний список гравців з Redis
    sb = await manager.scoreboard(r, roomCode)
    out = ServerStateSync(
        roomCode=roomCode,
        phase=state["phase"],
        questionIndex=state["questionIndex"],
        startedAt=None,
        durationMs=None,
        question=None,
        scoreboard=sb,  # Використовуємо актуальний scoreboard
        reveal=None,
        playerId=None,
    )
    
    await manager.broadcast(roomCode, json.loads(out.model_dump_json()))

async def handle_start_question(websocket: WebSocket, r, roomCode: str, evt: HostStartQuestion) -> None:
    msg = await manager.start_question(r, roomCode, evt.questionIndex, evt.durationMs)
    await manager.broadcast(roomCode, msg)

async def handle_next_question(websocket: WebSocket, r, roomCode: str, evt: HostNextQuestion) -> None:
    duration_ms = evt.durationMs
    state = await manager.get_state(r, roomCode)
    current_idx = state.get("questionIndex", -1)
    next_idx = current_idx + 1
    questions = await manager.load_questions(r, roomCode)
    
    if next_idx >= len(questions):
        await send_error(websocket, "Це було останнє питання")
        return

    msg = await manager.start_question(r, roomCode, next_idx, duration_ms)
    await manager.broadcast(roomCode, msg)

async def handle_reveal_answer(websocket: WebSocket, r, roomCode: str, evt: HostRevealAnswer) -> None:
    state = await manager.get_state(r, roomCode)
    current_idx = evt.questionIndex or state.get("questionIndex", -1)
    msg = await manager.reveal_answer(r, roomCode, current_idx)
    sb = await manager.scoreboard(r, roomCode)
    msg["scoreboard"] = sb
    await manager.broadcast(roomCode, msg)

async def handle_end_session(websocket: WebSocket, r, roomCode: str, session_key: str) -> None:
    await manager.set_state(r, roomCode, phase="ENDED")
    sb = await manager.scoreboard(r, roomCode)
    session_raw = await r.get(session_key)
    session_data = json.loads(session_raw) if session_raw else {}
    
    session_id = session_data.get("sessionId") or str(uuid.uuid4())
    quiz_id = session_data.get("quizId")
    created_at_ms = session_data.get("createdAt") or int(time.time() * 1000)
    ended_at_ms = int(time.time() * 1000)

    session_data.update({"phase": "ENDED", "endedAt": ended_at_ms})
    await r.set(session_key, json.dumps(session_data))

    questions = await manager.load_questions(r, roomCode)
    snapshot = FinishedSessionSnapshot(
        sessionId=session_id,
        roomCode=roomCode,
        quizId=quiz_id,
        createdAt=created_at_ms,
        endedAt=ended_at_ms,
        questions=questions,
        scoreboard=sb,
    )
    
    archive_key = f"quiz:session:{session_id}"
    await r.set(archive_key, snapshot.model_dump_json())
    await r.zadd("quiz:session:index", {session_id: ended_at_ms})
    await r.sadd(f"quiz:room_sessions:{roomCode}", session_id)

    try:
        session_service = QuizSessionService()
        session_service.save_finished_session(snapshot.model_dump())
    except Exception as e:
        print(f"Помилка збереження в Supabase: {e}")

    await manager.cleanup_room_data(r, roomCode)
    await r.delete(f"quiz:session_meta:{roomCode}")
    await r.delete(session_key)
    await delete_room_quiz(r, roomCode)

    await manager.broadcast(roomCode, {"type": "session_ended", "scoreboard": sb, "sessionId": session_id})

async def handle_player_join(websocket: WebSocket, r, roomCode: str, evt: PlayerJoin, player_id: str | None, player_name: str | None) -> None:
    pass

async def handle_player_answer(websocket: WebSocket, r, roomCode: str, evt: PlayerAnswer, player_id: str | None) -> None:
    if player_id is None:
        await send_error(websocket, "Player not registered")
        return
    ok = await manager.submit_answer(r, roomCode, evt.questionIndex, player_id, evt.optionIndex)
    await websocket.send_text(json.dumps({"type": "answer_ack", "ok": ok}))


async def monitor_host_disconnect(r, roomCode: str) -> None:
    """
    Моніторить відсутність хоста. Якщо хост не повертається протягом 1 хвилини
    після відключення, відправляє connection_closed всім гравцям.
    """
    try:
        # Чекаємо 1 хвилину
        await asyncio.sleep(60)
        
        # Перевіряємо, чи хост повернувся (ключ має бути видалений, якщо хост підключився)
        presence_exists = await r.exists(manager.k_host_presence(roomCode))
        if presence_exists:
            # Хост не повернувся - відправляємо connection_closed всім гравцям
            state = await manager.get_state(r, roomCode)
            # Перевіряємо, що ми все ще в фазі LOBBY
            if state.get("phase") == "LOBBY":
                print(f"[monitor_host_disconnect] Хост не повернувся для кімнати {roomCode}, відправляємо connection_closed")
                await manager.broadcast(
                    roomCode,
                    {
                        "type": "connection_closed",
                        "message": "Хост вийшов з кімнати. Вікторина скасована.",
                    },
                )
                # Видаляємо ключ після відправки повідомлення
                await r.delete(manager.k_host_presence(roomCode))
    except asyncio.CancelledError:
        print(f"[monitor_host_disconnect] Моніторинг скасовано для {roomCode}")
        # Якщо таймер скасовано (хост повернувся), видаляємо ключ
        await r.delete(manager.k_host_presence(roomCode))
    except Exception as e:
        print(f"[monitor_host_disconnect] Помилка: {e}")