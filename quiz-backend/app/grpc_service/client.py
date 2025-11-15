import asyncio
import grpc
from typing import Optional

from app.core.config import settings
from app.grpc_service.generated import room_code_pb2
from app.grpc_service.generated.room_code_pb2_grpc import RoomCodeServiceStub


class RoomCodeClient:
    def __init__(self, host: str, port: int):
        self._target = f"{host}:{port}"
        self.channel: grpc.aio.Channel = grpc.aio.insecure_channel(self._target)
        self.stub = RoomCodeServiceStub(self.channel)

    async def connect(self, timeout: float = 5.0):
        try:
            await asyncio.wait_for(self.channel.channel_ready(), timeout=timeout)
        except Exception as e:
            raise ConnectionError(f"gRPC channel not ready: {e}") from e

    async def close(self):
        try:
            await self.channel.close()
        except Exception:
            pass

    async def generate_room_code(
        self,
        quiz_id: str,
        code_length: int = 6,
        ttl_seconds: int = 21600,
    ) -> str:
        req = room_code_pb2.GenerateRoomCodeRequest(
            quiz_id=quiz_id,
            code_length=code_length,
            ttl_seconds=ttl_seconds,
        )
        resp = await self.stub.GenerateRoomCode(req)
        return resp.room_code

    async def resolve_room_code(self, room_code: str) -> Optional[str]:
        req = room_code_pb2.ResolveRoomCodeRequest(room_code=room_code)
        resp = await self.stub.ResolveRoomCode(req)
        return resp.quiz_id if resp.found else None

    async def delete_room_code(self, room_code: str) -> bool:
        req = room_code_pb2.DeleteRoomCodeRequest(room_code=room_code)
        resp = await self.stub.DeleteRoomCode(req)
        return resp.deleted


# ---------------------------
# Singleton client
# ---------------------------

_client: Optional[RoomCodeClient] = None


def get_room_code_client() -> RoomCodeClient:
    """
    Return singleton RoomCodeClient using settings.grpc_host/settings.grpc_port.
    """
    global _client
    if _client is None:
        _client = RoomCodeClient(
           host=settings.GRPC_HOST,
           port=settings.GRPC_PORT,
        )
    return _client
