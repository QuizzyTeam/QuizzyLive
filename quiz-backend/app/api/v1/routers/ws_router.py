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
from app.grpc_service.client import get_room_code_client


ws_router = APIRouter()
manager = RoomManager()


async def send_error(websocket: WebSocket, message: str) -> None:
    """Допоміжна функція для надсилання помилок"""
    await websocket.send_text(
        json.dumps(
            {
                "type": "error",
                "message": message,
            }
        )
    )


@ws_router.websocket("/ws")
async def ws_endpoint(
    websocket: WebSocket,
    role: str = Query(regex="^(host|player)$"),
    roomCode: str = Query(...),
    name: str | None = None,
    playerId: str | None = Query(default=None),
) -> None:
    print("\n" + "=" * 60)
    print("New WebSocket request:")
    print(f" Role: {role}")
    print(f" RoomCode: {roomCode}")
    print(f" Name: {name}")
    print("=" * 60 + "\n")

    r = await get_redis()
    
    # Резолвінг коду через gRPC
    actual_quiz_id = roomCode
    
    if len(roomCode) < 20:
        print(f"Resolving short code: {roomCode}")
        grpc_client = get_room_code_client()
        
        try:
            resolved_id = await grpc_client.resolve_room_code(roomCode)
            if resolved_id:
                actual_quiz_id = resolved_id
                print(f"Code {roomCode} resolved to quiz_id {actual_quiz_id}")
            else:
                error_msg = "Room code not found or expired"
                print(f"Error: {error_msg}")
                await send_error(websocket, error_msg)
                await websocket.close()
                return
        except Exception as e:
            error_msg = f"Error resolving code: {str(e)}"
            print(f"Error: {error_msg}")
            await send_error(websocket, error_msg)
            await websocket.close()
            return
    
    await manager.register(actual_quiz_id, websocket)

    player_id: str | None = None
    player_name: str | None = None
    session_key = f"session:{actual_quiz_id}"

    try:
        if role == "player":
            print(f"Processing PLAYER connection: {name}")
            
            session_raw = await r.get(session_key)
            session_exists = session_raw is not None
            print(f" Session check {session_key}: {'EXISTS' if session_exists else 'NOT FOUND'}")
            
            if not session_exists:
                error_msg = "Quiz not found or not created yet"
                print(error_msg)
                await send_error(websocket, error_msg)
                await websocket.close()
                return

            session_data = json.loads(session_raw)
            if session_data.get("phase") == "ENDED":
                error_msg = "Quiz already ended"
                print(error_msg)
                await send_error(websocket, error_msg)
                await websocket.close()
                return

            if playerId is not None:
                stored_name = await r.hget(manager.k_players(actual_quiz_id), playerId)
                if stored_name is not None:
                    player_id = playerId
                    player_name = stored_name
                    print(f"Restored player by playerId={player_id[:8]}")
                else:
                    print("Provided playerId not found in Redis")

            if player_id is None and name:
                all_players = await r.hgetall(manager.k_players(actual_quiz_id))
                for pid, pname in all_players.items():
                    if pname == name:
                        player_id = pid
                        player_name = pname
                        print(f"Restored player by name, player_id={player_id[:8]}")
                        break

            if player_id is None:
                player_id = str(uuid.uuid4())
                player_name = name or "Player"
                print(f"Created new player_id: {player_id[:8]}")

            await r.hset(
                manager.k_players(actual_quiz_id), mapping={player_id: player_name}
            )
            await r.expire(manager.k_players(actual_quiz_id), 6 * 60 * 60)

            state = await manager.get_state(r, actual_quiz_id)
            questions = await manager.load_questions(r, actual_quiz_id)
            qidx = state.get("questionIndex", -1)
            question = questions[qidx] if 0 <= qidx < len(questions) else None
            sb = await manager.scoreboard(r, actual_quiz_id)

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
            
            print("Sending state_sync to player")
            await websocket.send_text(ss.model_dump_json())

            await manager.broadcast(
                actual_quiz_id,
                {
                    "type": "player_joined",
                    "playerName": player_name,
                    "playerId": player_id,
                    "roomCode": roomCode,
                },
                exclude=websocket,
            )
            print(f"Player {player_name} successfully connected")

        elif role == "host":
            print(f"Processing HOST connection for room: {roomCode} (quiz_id: {actual_quiz_id})")
            
            state = await manager.get_state(r, actual_quiz_id)
            questions = await manager.load_questions(r, actual_quiz_id)
            qidx = state.get("questionIndex", -1)
            question = questions[qidx] if 0 <= qidx < len(questions) else None
            sb = await manager.scoreboard(r, actual_quiz_id)

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
            
            print(f"Sending state_sync to host with {len(sb)} participants")
            await websocket.send_text(ss.model_dump_json())
            print("Host successfully connected")

        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            event_type = data.get("type")
            
            print(f"\nReceived event: {event_type} from {role}")

            try:
                if event_type == "host:create_session":
                    evt = HostCreateSession(**data)
                    await handle_create_session(websocket, r, actual_quiz_id, roomCode, evt, session_key)

                elif event_type == "host:start_question":
                    evt = HostStartQuestion(**data)
                    await handle_start_question(websocket, r, actual_quiz_id, evt)

                elif event_type == "host:next_question":
                    evt = HostNextQuestion(**data)
                    await handle_next_question(websocket, r, actual_quiz_id, evt)

                elif event_type == "host:reveal_answer":
                    evt = HostRevealAnswer(**data)
                    await handle_reveal_answer(websocket, r, actual_quiz_id, evt)

                elif event_type == "host:end_session":
                    evt = HostEndSession(**data)
                    await handle_end_session(websocket, r, actual_quiz_id, roomCode, session_key)

                elif event_type == "player:join":
                    evt = PlayerJoin(**data)
                    await handle_player_join(
                        websocket, r, actual_quiz_id, evt, player_id, player_name
                    )

                elif event_type == "player:answer":
                    evt = PlayerAnswer(**data)
                    await handle_player_answer(websocket, r, actual_quiz_id, evt, player_id)

                else:
                    await send_error(websocket, f"Unknown event type: {event_type}")

            except ValidationError as e:
                error_msg = f"Validation error: {str(e)}"
                print(error_msg)
                await send_error(websocket, error_msg)

    except WebSocketDisconnect:
        print(f"\nDisconnected: {role} ({player_name or 'host'}) from {roomCode}")
    except Exception as e:
        print(f"\nWebSocket error: {str(e)}")
        import traceback
        traceback.print_exc()
        try:
            await send_error(websocket, str(e))
        except Exception:
            pass
    finally:
        print(f"Cleanup for {role} ({player_name or 'host'})")
        await manager.unregister(actual_quiz_id, websocket)


async def handle_create_session(
    websocket: WebSocket,
    r,
    actual_quiz_id: str,
    original_room_code: str,
    evt: HostCreateSession,
    session_key: str,
) -> None:
    print("Creating session")
    
    quiz_id = evt.quizId or actual_quiz_id
    questions = [q.model_dump() for q in evt.questions]
    
    print(f" QuizId: {quiz_id}")
    print(f" Questions: {len(questions)}")

    if not questions and quiz_id:
        print("Loading questions from DB")
        try:
            from app.services.quiz_service import QuizService
            from app.repositories.quiz_repository import QuizRepository
            from app.core.supabase_client import get_supabase
            
            repo = QuizRepository(get_supabase())
            svc = QuizService(repo)
            quiz_data = svc.get_quiz(quiz_id)
            questions = quiz_data["questions"]
            print(f"Loaded {len(questions)} questions")
        except Exception as e:
            await send_error(websocket, f"Error loading questions: {str(e)}")
            return

    session_id = str(uuid.uuid4())
    created_at_ms = int(time.time() * 1000)

    session_data = {
        "sessionId": session_id,
        "roomCode": original_room_code,
        "quizId": quiz_id,
        "questions": questions,
        "phase": "LOBBY",
        "questionIndex": -1,
        "players": [],
        "createdAt": created_at_ms,
    }
    await r.set(session_key, json.dumps(session_data))
    print(f"Saved {session_key} with sessionId={session_id}")

    await manager.create_session(r, actual_quiz_id, questions, session_id, created_at_ms)

    state = await manager.get_state(r, actual_quiz_id)
    out = ServerStateSync(
        roomCode=original_room_code,
        phase=state["phase"],
        questionIndex=state["questionIndex"],
        startedAt=None,
        durationMs=None,
        question=None,
        scoreboard=[],
        reveal=None,
        playerId=None,
    )
    
    print("Broadcasting state_sync to all")
    await manager.broadcast(actual_quiz_id, json.loads(out.model_dump_json()))


async def handle_start_question(
    websocket: WebSocket, r, actual_quiz_id: str, evt: HostStartQuestion
) -> None:
    print(f"Starting question {evt.questionIndex} with duration {evt.durationMs}ms")
    
    msg = await manager.start_question(r, actual_quiz_id, evt.questionIndex, evt.durationMs)
    await manager.broadcast(actual_quiz_id, msg)


async def handle_next_question(
    websocket: WebSocket, r, actual_quiz_id: str, evt: HostNextQuestion
) -> None:
    print("Starting next question")
    
    duration_ms = evt.durationMs
    print(f" Duration: {duration_ms}ms")

    state = await manager.get_state(r, actual_quiz_id)
    current_idx = state.get("questionIndex", -1)
    next_idx = current_idx + 1

    questions = await manager.load_questions(r, actual_quiz_id)
    
    if next_idx >= len(questions):
        await send_error(websocket, "This was the last question")
        return

    msg = await manager.start_question(r, actual_quiz_id, next_idx, duration_ms)
    print("Broadcasting question_started")
    await manager.broadcast(actual_quiz_id, msg)


async def handle_reveal_answer(
    websocket: WebSocket, r, actual_quiz_id: str, evt: HostRevealAnswer
) -> None:
    print("Revealing answer")
    
    state = await manager.get_state(r, actual_quiz_id)
    current_idx = evt.questionIndex or state.get("questionIndex", -1)
    
    print(f" Question index: {current_idx}")

    msg = await manager.reveal_answer(r, actual_quiz_id, current_idx)
    sb = await manager.scoreboard(r, actual_quiz_id)
    msg["scoreboard"] = sb

    print(f"Broadcasting answer_revealed with scoreboard ({len(sb)} players)")
    await manager.broadcast(actual_quiz_id, msg)


async def handle_end_session(
    websocket: WebSocket,
    r,
    actual_quiz_id: str,
    original_room_code: str,
    session_key: str
) -> None:
    print("Ending session")

    await manager.set_state(r, actual_quiz_id, phase="ENDED")
    sb = await manager.scoreboard(r, actual_quiz_id)

    session_raw = await r.get(session_key)
    session_data = json.loads(session_raw) if session_raw else {}
    
    session_id = session_data.get("sessionId") or str(uuid.uuid4())
    quiz_id = session_data.get("quizId") or actual_quiz_id
    created_at_ms = session_data.get("createdAt") or int(time.time() * 1000)
    ended_at_ms = int(time.time() * 1000)

    session_data.update({
        "sessionId": session_id,
        "quizId": quiz_id,
        "createdAt": created_at_ms,
        "phase": "ENDED",
        "endedAt": ended_at_ms,
    })
    await r.set(session_key, json.dumps(session_data))

    questions = await manager.load_questions(r, actual_quiz_id)
    snapshot = FinishedSessionSnapshot(
        sessionId=session_id,
        roomCode=original_room_code,
        quizId=quiz_id,
        createdAt=created_at_ms,
        endedAt=ended_at_ms,
        questions=questions,
        scoreboard=sb,
    )

    archive_key = f"quiz:session:{session_id}"
    await r.set(archive_key, snapshot.model_dump_json())
    await r.zadd("quiz:session:index", {session_id: ended_at_ms})
    await r.sadd(f"quiz:room_sessions:{original_room_code}", session_id)
    
    print(f"Saved session archive to {archive_key}")

    try:
        session_service = QuizSessionService()
        session_service.save_finished_session(snapshot.model_dump())
        print(f"Session {session_id} saved to Supabase")
    except Exception as e:
        print(f"Error saving session to Supabase: {e}")

    # Видаляємо код кімнати через gRPC
    try:
        grpc_client = get_room_code_client()
        await grpc_client.delete_room_code(original_room_code)
        print(f"Room code {original_room_code} deleted via gRPC")
    except Exception as e:
        print(f"Warning: Failed to delete room code: {e}")

    await manager.cleanup_room_data(r, actual_quiz_id)

    print("Broadcasting session_ended")
    await manager.broadcast(
        actual_quiz_id,
        {
            "type": "session_ended",
            "scoreboard": sb,
            "sessionId": session_id,
        },
    )


async def handle_player_join(
    websocket: WebSocket,
    r,
    actual_quiz_id: str,
    evt: PlayerJoin,
    player_id: str | None,
    player_name: str | None,
) -> None:
    print("Explicit player join (legacy)")
    
    if player_id is None:
        player_id = str(uuid.uuid4())
        player_name = evt.name
        print(f" Created new player_id: {player_id[:8]}")

    await r.hset(manager.k_players(actual_quiz_id), mapping={player_id: evt.name})
    await r.expire(manager.k_players(actual_quiz_id), 6 * 60 * 60)

    await websocket.send_text(
        json.dumps(
            {
                "type": "player_joined",
                "playerId": player_id,
                "playerName": evt.name,
            }
        )
    )

    await manager.broadcast(
        actual_quiz_id,
        {
            "type": "player_joined",
            "playerName": evt.name,
            "playerId": player_id,
        },
        exclude=websocket,
    )


async def handle_player_answer(
    websocket: WebSocket,
    r,
    actual_quiz_id: str,
    evt: PlayerAnswer,
    player_id: str | None,
) -> None:
    print("Player answer")
    
    if player_id is None:
        await send_error(websocket, "Player not registered")
        return

    print(f" Player: {player_id[:8]}")
    print(f" Question: {evt.questionIndex}, Option: {evt.optionIndex}")

    ok = await manager.submit_answer(
        r, actual_quiz_id, evt.questionIndex, player_id, evt.optionIndex
    )

    print(f" Result: {'OK' if ok else 'REJECTED'}")
    
    await websocket.send_text(
        json.dumps(
            {
                "type": "answer_ack",
                "ok": ok,
            }
        )
    )