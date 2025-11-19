# quiz-backend/app/core/grpc_client.py
import grpc
import os
from app.protos import room_pb2, room_pb2_grpc

GRPC_HOST = os.getenv("GRPC_HOST", "localhost:50052")

class GrpcClient:
    def __init__(self):
        self.channel = grpc.insecure_channel(GRPC_HOST)
        if room_pb2_grpc:
            self.stub = room_pb2_grpc.RoomCodeGeneratorStub(self.channel)
        else:
            self.stub = None

    def get_new_room_code(self, length: int = 6) -> str:
        if not self.stub:
            # Fallback якщо gRPC недоступний або не налаштований
            import random, string
            return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
        
        try:
            request = room_pb2.GenerateCodeRequest(length=length)
            response = self.stub.GenerateCode(request)
            return response.code
        except grpc.RpcError as e:
            print(f"gRPC error: {e}")
            # Fallback
            import random, string
            return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

grpc_client = GrpcClient()