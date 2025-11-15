cd quiz-backend
.\.venv\Scripts\Activate
uvicorn app.main:app --reload

python -m app.grpc_service.server

python -m grpc_tools.protoc -I app\grpc_service\protos --python_out=app\grpc_service\generated --grpc_python_out=app\grpc_service\generated app\grpc_service\protos\room_code.proto
