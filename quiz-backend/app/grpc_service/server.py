import asyncio
import random
import string
import time
import grpc

# ВАЖЛИВО: імпорт з app.grpc_service.generated
from app.grpc_service.generated import room_code_pb2, room_code_pb2_grpc

# Використовуємо глобальний Redis клієнт
from app.core.redis_manager import get_redis


class RoomCodeServicer(room_code_pb2_grpc.RoomCodeServiceServicer):

    def __init__(self):
        self.redis = None

    async def _get_redis(self):
        # Використовуємо глобальне з'єднання з redis_manager
        if self.redis is None:
            self.redis = await get_redis()
        return self.redis

    def _generate_code(self, length: int = 6) -> str:
        chars = string.ascii_uppercase + string.digits
        chars = chars.replace('O', '').replace('I', '').replace('0', '')
        return ''.join(random.choices(chars, k=length))

    async def GenerateRoomCode(
        self,
        request: room_code_pb2.GenerateRoomCodeRequest,
        context: grpc.aio.ServicerContext
    ) -> room_code_pb2.GenerateRoomCodeResponse:
        try:
            redis = await self._get_redis()

            quiz_id = request.quiz_id
            code_length = request.code_length if request.code_length > 0 else 6
            ttl_seconds = request.ttl_seconds if request.ttl_seconds > 0 else 6 * 60 * 60

            if not quiz_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("quiz_id is required")
                return room_code_pb2.GenerateRoomCodeResponse()

            # Спроби згенерувати унікальний код
            max_attempts = 10
            room_code = None

            for _ in range(max_attempts):
                candidate = self._generate_code(code_length)
                key = f"room_code:{candidate}"

                exists = await redis.exists(key)
                if not exists:
                    room_code = candidate
                    break

            if room_code is None:
                context.set_code(grpc.StatusCode.RESOURCE_EXHAUSTED)
                context.set_details("Failed to generate unique code after 10 attempts")
                return room_code_pb2.GenerateRoomCodeResponse()

            # Запис у Redis
            key = f"room_code:{room_code}"
            await redis.set(key, quiz_id, ex=ttl_seconds)

            reverse_key = f"quiz_code:{quiz_id}"
            await redis.set(reverse_key, room_code, ex=ttl_seconds)

            expires_at = int(time.time()) + ttl_seconds

            print(f"Generated code: {room_code} for quiz_id: {quiz_id}")

            return room_code_pb2.GenerateRoomCodeResponse(
                room_code=room_code,
                quiz_id=quiz_id,
                expires_at=expires_at
            )

        except Exception as e:
            print(f"Error in GenerateRoomCode: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return room_code_pb2.GenerateRoomCodeResponse()

    async def ResolveRoomCode(
        self,
        request: room_code_pb2.ResolveRoomCodeRequest,
        context: grpc.aio.ServicerContext
    ) -> room_code_pb2.ResolveRoomCodeResponse:
        try:
            redis = await self._get_redis()
            room_code = request.room_code

            if not room_code:
                return room_code_pb2.ResolveRoomCodeResponse(
                    found=False,
                    error_message="room_code is required"
                )

            key = f"room_code:{room_code}"
            quiz_id = await redis.get(key)

            if quiz_id is None:
                print(f"Code not found: {room_code}")
                return room_code_pb2.ResolveRoomCodeResponse(
                    found=False,
                    error_message="Room code not found or expired"
                )

            print(f"Resolved: {room_code} -> {quiz_id}")

            return room_code_pb2.ResolveRoomCodeResponse(
                found=True,
                quiz_id=quiz_id,
                error_message=""
            )

        except Exception as e:
            print(f"Error in ResolveRoomCode: {e}")
            return room_code_pb2.ResolveRoomCodeResponse(
                found=False,
                error_message=str(e)
            )

    async def DeleteRoomCode(
        self,
        request: room_code_pb2.DeleteRoomCodeRequest,
        context: grpc.aio.ServicerContext
    ) -> room_code_pb2.DeleteRoomCodeResponse:
        try:
            redis = await self._get_redis()
            room_code = request.room_code

            if not room_code:
                return room_code_pb2.DeleteRoomCodeResponse(deleted=False)

            key = f"room_code:{room_code}"
            quiz_id = await redis.get(key)

            deleted = await redis.delete(key)

            if quiz_id:
                reverse_key = f"quiz_code:{quiz_id}"
                await redis.delete(reverse_key)

            print(f"Deleted code: {room_code}")

            return room_code_pb2.DeleteRoomCodeResponse(deleted=bool(deleted))

        except Exception as e:
            print(f"Error in DeleteRoomCode: {e}")
            return room_code_pb2.DeleteRoomCodeResponse(deleted=False)


async def serve(host: str = "0.0.0.0", port: int = 50051):
    server = grpc.aio.server()

    servicer = RoomCodeServicer()
    room_code_pb2_grpc.add_RoomCodeServiceServicer_to_server(servicer, server)

    server.add_insecure_port(f"{host}:{port}")

    print(f"gRPC server started on {host}:{port}")

    await server.start()

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        print("\nStopping server...")
        await servicer.close()
        await server.stop(grace=5)


if __name__ == "__main__":
    import os

    HOST = os.getenv("GRPC_HOST", "0.0.0.0")
    PORT = int(os.getenv("GRPC_PORT", "50051"))

    asyncio.run(serve(host=HOST, port=PORT))
