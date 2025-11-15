import React, { useEffect, useState, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { quizApi } from "../../api/quizApi";
import { createQuizSocket } from "../../api/wsClient";
import "./QuizLobbyPage.css";

function QuizLobbyPage() {
  const navigate = useNavigate();
  const { id } = useParams(); // Це roomCode
  const [quiz, setQuiz] = useState(null);
  const [realQuizId, setRealQuizId] = useState(null);
  const [participants, setParticipants] = useState([]);
  const [ws, setWs] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const wsInitialized = useRef(false);

  // 1. resolve roomCode → quizId
  useEffect(() => {
    const fetchQuiz = async () => {
      try {
        setLoading(true);

        const resolved = await quizApi.resolveRoomCode(id);
        const quizId = resolved.quiz_id;
        setRealQuizId(quizId);

        const q = await quizApi.getById(quizId);
        setQuiz(q);
      } catch (e) {
        setError(e.message || "Помилка завантаження вікторини");
      } finally {
        setLoading(false);
      }
    };
    fetchQuiz();
  }, [id]);

  // 2. WebSocket створення сесії
  useEffect(() => {
    if (!quiz || !realQuizId || wsInitialized.current) return;

    wsInitialized.current = true;

    const socket = createQuizSocket({
      role: "host",
      roomCode: id,
      onMessage: (msg) => {
        console.log("host отримав:", msg);

        if (msg.type === "state_sync") {
          if (msg.phase === "LOBBY" && msg.scoreboard) {
            setParticipants(msg.scoreboard);
          }
        } else if (msg.type === "player_joined") {
          setParticipants((prev) => {
            const exists = prev.find((p) => p.name === msg.playerName);
            if (exists) return prev;
            return [...prev, { name: msg.playerName, score: 0 }];
          });
        } else if (msg.type === "player_left") {
          setParticipants((prev) =>
            prev.filter((p) => p.name !== msg.playerName)
          );
        }
      },
    });

    socket.onopen = () => {
      console.log("WebSocket відкрито (host)");

      const questions = quiz.questions.map((q) => ({
        id: q.id,
        question_text: q.questionText || q.question_text,
        answers: q.answers,
        correct_answer:
          q.correctAnswer !== undefined ? q.correctAnswer : q.correct_answer,
        position: q.position !== undefined ? q.position : 0,
      }));

      socket.sendJson({
        type: "host:create_session",
        roomCode: id,
        quizId: realQuizId,
        questions: questions,
      });
    };

    socket.onerror = (err) => console.error("WebSocket помилка:", err);
    socket.onclose = () => {
      console.warn("WebSocket закрито (host)");
      wsInitialized.current = false;
    };

    setWs(socket);

    return () => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.close();
      }
      wsInitialized.current = false;
    };
  }, [quiz, realQuizId, id]);

  // 3. Старт гри
  const handleStartQuiz = () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      alert("WebSocket не підключено!");
      return;
    }

    navigate(`/host-play/${realQuizId}?room=${id}`);
  };

  const handleCancel = () => {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.close();
    }
    navigate("/hostDashboard");
  };

  const handleCopyCode = () => {
    navigator.clipboard.writeText(id);
    alert(`Код вікторини скопійовано!`);
  };

  return (
    <div className="lobby-container">
      <div className="lobby-header">
        <button className="cancel-btn" onClick={handleCancel}>
          Назад
        </button>
        <h1>{quiz?.title || "Завантаження..."}</h1>
      </div>

      {error ? (
        <p className="error-text">{error}</p>
      ) : (
        <div className="lobby-content">
          <div className="lobby-code-box">
            <h2>Код для підключення:</h2>
            <div className="code">{id}</div>
            <button className="copy-btn" onClick={handleCopyCode}>
              Скопіювати код
            </button>
            <p className="hint-text">
              Передайте цей код учасникам для підключення до вікторини
            </p>
          </div>

          <div className="participants-box">
            <h3>Учасники ({participants.length}):</h3>
            {participants.length === 0 ? (
              <p>Очікуємо учасників...</p>
            ) : (
              <ul className="participants-list">
                {participants.map((p, i) => (
                  <li key={i} className="participant-item">
                    <span className="participant-avatar">👤</span>
                    <span className="participant-name">{p.name}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <button
            className="start-quiz-btn"
            onClick={handleStartQuiz}
            disabled={loading || !ws || ws.readyState !== WebSocket.OPEN}
          >
            Почати вікторину
          </button>

          {ws?.readyState !== WebSocket.OPEN && !loading && (
            <p className="warning-text">Підключення до сервера...</p>
          )}
        </div>
      )}
    </div>
  );
}

export default QuizLobbyPage;
