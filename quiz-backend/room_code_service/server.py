# room-code-service/server.py
import grpc
from concurrent import futures
import random
import string
import os

# Потрібно згенерувати python код з proto файлу перед запуском
# python -m grpc_tools.protoc -I./protos --python_out=. --grpc_python_out=. ./protos/room.proto
import room_pb2
import room_pb2_grpc

class RoomCodeGenerator(room_pb2_grpc.RoomCodeGeneratorServicer):
    def GenerateCode(self, request, context):
        length = request.length if request.length > 0 else 4
        # Генеруємо випадковий код (літери + цифри)
        chars = string.ascii_uppercase + string.digits
        code = ''.join(random.choice(chars) for _ in range(length))
        return room_pb2.GenerateCodeResponse(code=code)

def server():
    port = os.getenv("GRPC_PORT", "50052")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    room_pb2_grpc.add_RoomCodeGeneratorServicer_to_server(RoomCodeGenerator(), server)
    server.add_insecure_port(f'[::]:{port}')
    print(f"gRPC Room Code Service started on port {port}")
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    server()