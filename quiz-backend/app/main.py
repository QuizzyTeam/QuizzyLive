import os
import subprocess
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI

from .core.config import settings
from .core.cors import setup_cors
from .api.v1.routers import quizzes as quizzes_router
from .api.v1.routers import ws_router



def compile_protos_if_needed():
    """Компілює proto файли при старті якщо потрібно."""
    generated_dir = Path("app/grpc_service/generated")
    pb2_file = generated_dir / "room_code_pb2.py"
    pb2_grpc_file = generated_dir / "room_code_pb2_grpc.py"

    if pb2_file.exists() and pb2_grpc_file.exists():
        print("Protobuf files already compiled, skipping...")
        return

    print("Compiling protobuf files...")
    generated_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "python", "-m", "grpc_tools.protoc",
        "-I", "app/grpc_service/protos",
        "--python_out=app/grpc_service/generated",
        "--grpc_python_out=app/grpc_service/generated",
        "app/grpc_service/protos/room_code.proto"
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        (generated_dir / "__init__.py").touch()
        Path("app/grpc_service/__init__.py").touch()
        print("Protobuf files compiled successfully")
    except subprocess.CalledProcessError as e:
        print(f"Error compiling protobuf: {e}")
        print("Make sure grpcio-tools is installed: pip install grpcio-tools")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events для FastAPI."""
    print("Starting FastAPI server...")

    # Компілюємо protobuf
    compile_protos_if_needed()

    # -----------------------------
    # gRPC client startup
    # -----------------------------
    try:
        from app.grpc_service.client import get_room_code_client
        grpc_client = get_room_code_client()

        try:
            await grpc_client.connect()
            print(f"Connected to gRPC server at {settings.GRPC_HOST}:{settings.GRPC_PORT}")
        except Exception as e:
            print(f"Warning: Could not connect to gRPC server at {settings.GRPC_HOST}:{settings.GRPC_PORT}: {e}")
            print("Room code generation features will be unavailable")

    except Exception as e:
        print(f"Warning: Could not initialize gRPC client: {e}")
        print("Room code generation features will be unavailable")

    # ---------------------------------------------------------------
    yield
    # ---------------------------------------------------------------

    print("Shutting down FastAPI server...")

    # -----------------------------
    # gRPC client shutdown
    # -----------------------------
    try:
        from app.grpc_service.client import get_room_code_client
        grpc_client = get_room_code_client()

        try:
            await grpc_client.close()
            print("gRPC connection closed")
        except Exception as e:
            print(f"Error closing gRPC connection: {e}")

    except Exception as e:
        print(f"Error during gRPC shutdown: {e}")


# ---------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------

app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan
)

setup_cors(app)

# Routers
app.include_router(quizzes_router.router, prefix=settings.API_V1_PREFIX)
app.include_router(ws_router.ws_router)



@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {
        "message": "QuizzyLive API",
        "status": "running",
        "features": [
            "REST API for quizzes",
            "WebSocket for real-time sessions",
            "gRPC for room code generation"
        ]
    }
