cd quiz-backend
.\.venv\Scripts\Activate
uvicorn app.main:app --reload

cd room_code_service
python -m server
