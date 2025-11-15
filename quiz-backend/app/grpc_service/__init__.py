import os
import subprocess
from pathlib import Path

def ensure_proto_compiled():
    """Компілює proto файли якщо їх ще немає"""
    generated_dir = Path(__file__).parent / "generated"
    pb2_file = generated_dir / "room_code_pb2.py"
    pb2_grpc_file = generated_dir / "room_code_pb2_grpc.py"
    
    # Якщо файли вже існують, пропускаємо компіляцію
    if pb2_file.exists() and pb2_grpc_file.exists():
        return
    
    print("Compiling protobuf files...")
    
    # Створюємо папку generated
    generated_dir.mkdir(exist_ok=True)
    
    # Компілюємо
    proto_dir = Path(__file__).parent / "protos"
    proto_file = proto_dir / "room_code.proto"
    
    cmd = [
        "python", "-m", "grpc_tools.protoc",
        f"-I{proto_dir}",
        f"--python_out={generated_dir}",
        f"--grpc_python_out={generated_dir}",
        str(proto_file)
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        
        # Створюємо __init__.py
        (generated_dir / "__init__.py").touch()
        
        print("Protobuf files compiled successfully")
    except subprocess.CalledProcessError as e:
        print(f"Error compiling protobuf: {e}")
        print(f"stderr: {e.stderr.decode()}")

# Компілюємо при імпорті модуля
ensure_proto_compiled()