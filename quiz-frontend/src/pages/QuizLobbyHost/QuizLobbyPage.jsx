import React, { useEffect, useState, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { sessionApi } from "../../api/sessionApi";
import { createQuizSocket } from "../../api/wsClient";
import "./QuizLobbyPage.css";

function QuizLobbyPage() {
  const navigate = useNavigate();
  const { id: roomCode } = useParams(); // Це roomCode (наприклад, 3JXPX)
  
  const [sessionData, setSessionData] = useState(null); // { quizId, quizTitle, status }
  const [participants, setParticipants] = useState([]);
  const [ws, setWs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  
  const wsInitialized = useRef(false);

  // 1. Завантаження даних сесії (без звернення до БД квізів на фронті)
  useEffect(() => {
    const initLobby = async () => {
      try {
        setLoading(true);
        // Отримуємо всю інфу про сесію (включаючи назву) з Redis через REST
        const info = await sessionApi.getInfo(roomCode);
        setSessionData(info);
      } catch (e) {
        console.error(e);
        setError("Сесію не знайдено або сталась помилка.");
        setTimeout(() => navigate("/hostDashboard"), 3000);
      } finally {
        setLoading(false);
      }
    };
    initLobby();
  }, [roomCode, navigate]);

  // 2. WebSocket
  useEffect(() => {
    if (!sessionData || wsInitialized.current) return;
    
    wsInitialized.current = true;

    const socket = createQuizSocket({
      role: "host",
      roomCode: roomCode,
      onMessage: (msg) => {
        if (msg.type === "state_sync") {
          // Завжди оновлюємо список учасників з scoreboard, якщо він є
          // Це важливо при перезавантаженні сторінки хоста
          if (msg.phase === "LOBBY") {
            if (msg.scoreboard && Array.isArray(msg.scoreboard)) {
              setParticipants(msg.scoreboard);
            } else {
              // Якщо scoreboard порожній, встановлюємо порожній масив
              setParticipants([]);
            }
          }
        } else if (msg.type === "player_joined") {
          setParticipants(prev => {
            // Перевіряємо, чи гравець вже є в списку (за playerId або name)
            const exists = prev.find(
              p => (p.playerId && p.playerId === msg.playerId) || 
                   (p.name === msg.playerName)
            );
            if (exists) {
              console.log("Гравець вже в списку:", msg.playerName);
              return prev;
            }
            console.log("Додаємо гравця:", msg.playerName);
            return [...prev, { 
              name: msg.playerName, 
              playerId: msg.playerId,
              score: 0 
            }];
          });
        } else if (msg.type === "player_left") {
          setParticipants(prev => 
            prev.filter(p => 
              p.name !== msg.playerName && 
              (!msg.playerId || p.playerId !== msg.playerId)
            )
          );
        }
      },
    });

    socket.onopen = () => {
      console.log("WS Connected");
      // Ініціалізуємо сесію. Питання НЕ передаємо, бекенд сам їх підтягне з БД по quizId
      socket.sendJson({
        type: "host:create_session",
        roomCode: roomCode,
        quizId: sessionData.quizId, 
        questions: [] // Пустий масив - сигнал бекенду завантажити з БД
      });
    };

    socket.onerror = (err) => console.error("WS Error:", err);
    socket.onclose = () => { wsInitialized.current = false; };
    setWs(socket);
    
    return () => {
      if (socket.readyState === WebSocket.OPEN) socket.close();
      wsInitialized.current = false;
    };
  }, [sessionData, roomCode]);

  const handleStartQuiz = () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      alert("WebSocket не підключено!");
      return;
    }
    navigate(`/host-play/${roomCode}`); 
  };

  const handleCancel = () => {
    if (ws?.readyState === WebSocket.OPEN) ws.close();
    navigate("/hostDashboard");
  };

  const handleCopyCode = () => {
    navigator.clipboard.writeText(roomCode);
    alert(`Код скопійовано!`);
  };

  return (
    <div className="lobby-container">
      <div className="lobby-header">
        <button className="cancel-btn" onClick={handleCancel}>Назад</button>
        {/* Відображаємо назву, яку повернув Redis */}
        <h1>{sessionData?.quizTitle || "Завантаження..."}</h1>
      </div>

      {error ? (
        <p className="error-text">{error}</p>
      ) : (
        <div className="lobby-content">
          <div className="lobby-code-box">
            <h2>Код для підключення:</h2>
            <div className="code">{roomCode}</div>
            <button className="copy-btn" onClick={handleCopyCode}>Скопіювати код</button>
          </div>

          <div className="participants-box">
            <h3>Учасники ({participants.length}):</h3>
            {participants.length === 0 ? (
              <p className="waiting-text">Очікуємо учасників...</p>
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
        </div>
      )}
    </div>
  );
}

export default QuizLobbyPage;