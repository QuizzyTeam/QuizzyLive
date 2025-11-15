import React, { useEffect, useState, useRef } from "react";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { quizApi } from "../../api/quizApi";
import { createQuizSocket } from "../../api/wsClient";
import "./QuizHostPlayPage.css";

function QuizHostPlayPage() {
  const navigate = useNavigate();
  const { id } = useParams(); // це quizId
  const location = useLocation();
  const roomCode = new URLSearchParams(location.search).get("room");

  const [ws, setWs] = useState(null);
  const [quiz, setQuiz] = useState(null);
  const [currentQuestion, setCurrentQuestion] = useState(null);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [scoreboard, setScoreboard] = useState([]);
  const [phase, setPhase] = useState("LOBBY");
  const [remainingTime, setRemainingTime] = useState(0);
  const [loading, setLoading] = useState(true);
  const [isSettingTime, setIsSettingTime] = useState(false);
  const [timeForQuestion, setTimeForQuestion] = useState(30);

  const wsInitialized = useRef(false);
  const timerRef = useRef(null);
  const questionEndTimeRef = useRef(null);

  // Перевірка roomCode
  useEffect(() => {
    if (!roomCode) {
      alert("Room code не передано!");
      navigate("/hostDashboard");
    }
  }, [roomCode]);

  const stopTimer = () => {
    questionEndTimeRef.current = null;
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setRemainingTime(0);
  };

  const startSyncedTimer = (startedAt, durationMs) => {
    if (!startedAt || !durationMs) {
      stopTimer();
      return;
    }

    const endTime = startedAt + durationMs;
    questionEndTimeRef.current = endTime;

    const computeRemaining = () =>
      Math.max(0, Math.ceil((endTime - Date.now()) / 1000));

    setRemainingTime(computeRemaining());

    timerRef.current = setInterval(() => {
      const r = computeRemaining();
      setRemainingTime(r);
      if (r <= 0) stopTimer();
    }, 250);
  };

  // Завантаження вікторини
  useEffect(() => {
    const fetchQuiz = async () => {
      try {
        const data = await quizApi.getById(id);
        setQuiz(data);
      } catch (err) {
        alert("Помилка завантаження: " + err.message);
        navigate("/hostDashboard");
      } finally {
        setLoading(false);
      }
    };

    fetchQuiz();
  }, [id, navigate]);

  // WebSocket підключення хоста
  useEffect(() => {
    if (!quiz || !roomCode || wsInitialized.current) return;

    wsInitialized.current = true;
    console.log("Підключення ведучого до кімнати:", roomCode);

    const socket = createQuizSocket({
      role: "host",
      roomCode: roomCode, // ← правильний код
      onMessage: (msg) => {
        console.log("Host (play) отримав:", msg);

        if (msg.type === "state_sync") {
          setPhase(msg.phase || "LOBBY");

          if (msg.scoreboard) setScoreboard(msg.scoreboard);
          if (msg.question) {
            setCurrentQuestion(msg.question);
            setQuestionIndex(msg.questionIndex || 0);
          }

          if (msg.phase === "QUESTION_ACTIVE") {
            startSyncedTimer(msg.startedAt, msg.durationMs);
          } else {
            stopTimer();
          }
        }

        if (msg.type === "question_started") {
          setCurrentQuestion(msg.question);
          setQuestionIndex(msg.questionIndex);
          setPhase("QUESTION_ACTIVE");
          setIsSettingTime(false);
          startSyncedTimer(msg.startedAt, msg.durationMs);
        }

        if (msg.type === "answer_revealed") {
          stopTimer();
          setPhase("REVEAL");
          if (msg.scoreboard) setScoreboard(msg.scoreboard);
        }

        if (msg.type === "player_joined") {
          setScoreboard((prev) => {
            const exists = prev.find(
              (p) =>
                p.name === msg.playerName || p.playerId === msg.playerId
            );
            if (exists) return prev;
            return [
              ...prev,
              {
                name: msg.playerName,
                playerId: msg.playerId,
                score: 0,
              },
            ];
          });
        }

        if (msg.type === "player_left") {
          setScoreboard((prev) =>
            prev.filter(
              (p) =>
                p.name !== msg.playerName &&
                p.playerId !== msg.playerId
            )
          );
        }
      },
    });

    socket.onopen = () => {
      console.log("WebSocket host (play) підключено");
    };

    socket.onerror = (err) => console.error("WebSocket помилка:", err);

    socket.onclose = () => {
      console.log("WebSocket закрито");
      stopTimer();
      wsInitialized.current = false;
    };

    setWs(socket);

    return () => {
      stopTimer();
      if (socket.readyState === WebSocket.OPEN) {
        socket.close();
      }
      wsInitialized.current = false;
    };
  }, [quiz, roomCode]);

  // Далі вся логіка (start question, reveal, next question…) — без змін
  // ↓↓↓ повністю залишаю без скорочень

  const handlePrepareQuestion = () => {
    if (!quiz || !quiz.questions || questionIndex >= quiz.questions.length) {
      alert("Це було останнє питання!");
      handleEndQuiz();
      return;
    }
    setIsSettingTime(true);
  };

  const handleStartQuestion = () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      alert("WebSocket не підключено!");
      return;
    }
    ws.sendJson({
      type: "host:next_question",
      durationMs: timeForQuestion * 1000,
    });
  };

  const handleRevealAnswer = () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.sendJson({ type: "host:reveal_answer" });
  };

  const handleNextQuestion = () => {
    const nextIndex = questionIndex + 1;
    if (nextIndex >= quiz.questions.length) {
      alert("Це було останнє питання!");
      handleEndQuiz();
    } else {
      setQuestionIndex(nextIndex);
      setPhase("LOBBY");
      setIsSettingTime(true);
      setTimeForQuestion(30);
      stopTimer();
    }
  };

  const handleEndQuiz = () => {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.sendJson({ type: "host:end_session" });
    }
    stopTimer();
    navigate("/hostDashboard");
  };

  // Rendering (повний, не урізаний)

  if (loading) {
    return (
      <div className="quiz-play-container loading">
        <p>⏳ Завантаження...</p>
      </div>
    );
  }

  if (!quiz) {
    return (
      <div className="quiz-play-container error">
        <p>Вікторину не знайдено</p>
      </div>
    );
  }

  const totalQuestions = quiz.questions.length;
  const currentPreview = quiz.questions[questionIndex];
  const isTimeCritical = remainingTime <= 5 && remainingTime > 0;

  return (
    <div className="quiz-play-container">
      <header className="quiz-header">
        <h1>{quiz.title}</h1>
        <div className="header-info">
          <span>
            Питання {questionIndex + 1} / {totalQuestions}
          </span>
          <span>Учасників: {scoreboard.length}</span>
        </div>
        <button className="end-quiz-btn" onClick={handleEndQuiz}>
          Завершити
        </button>
      </header>

      <div className="host-content">
        {isSettingTime && (
          <section className="time-setting-box">
            <h2>Встановіть час для питання</h2>
            <p className="question-preview">{currentPreview.questionText}</p>
            <div className="time-input-group">
              <input
                type="number"
                min="5"
                max="300"
                value={timeForQuestion}
                onChange={(e) => setTimeForQuestion(Number(e.target.value))}
                className="time-input"
              />
            </div>
            <button className="start-question-btn" onClick={handleStartQuestion}>
              Почати питання
            </button>
          </section>
        )}

        {phase === "QUESTION_ACTIVE" && currentQuestion && (
          <section className="question-active-box">
            <div
              className={
                "timer-display" + (isTimeCritical ? " time-critical" : "")
              }
            >
              {remainingTime}с
            </div>
            <div className="question-box">
              <h2>{currentQuestion.question_text}</h2>
            </div>
            <ul className="answers-list">
              {currentQuestion.answers.map((answer, idx) => (
                <li key={idx} className="answer-option">
                  <span className="option-number">{idx + 1}</span>
                  <span className="option-text">{answer}</span>
                </li>
              ))}
            </ul>
            <button className="reveal-btn" onClick={handleRevealAnswer}>
              Показати відповідь
            </button>
          </section>
        )}

        {phase === "REVEAL" && currentQuestion && (
          <section className="reveal-box">
            <h2>Правильна відповідь:</h2>
            <p>{currentQuestion.question_text}</p>
            <ul className="answers-list">
              {currentQuestion.answers.map((answer, idx) => (
                <li
                  key={idx}
                  className={
                    "answer-option" +
                    (idx === currentQuestion.correct_answer ? " correct" : "")
                  }
                >
                  <span className="option-number">{idx + 1}</span>
                  <span className="option-text">{answer}</span>
                </li>
              ))}
            </ul>

            {questionIndex < totalQuestions - 1 ? (
              <button className="next-btn" onClick={handleNextQuestion}>
                Наступне питання
              </button>
            ) : (
              <button className="finish-btn" onClick={handleEndQuiz}>
                Завершити вікторину
              </button>
            )}
          </section>
        )}

        {(phase === "LOBBY" || phase === "WAITING") && !isSettingTime && (
          <section className="waiting-box">
            <p>Готово до старту</p>
            <button className="prepare-btn" onClick={handlePrepareQuestion}>
              Підготувати питання
            </button>
          </section>
        )}

        <section className="scoreboard-section">
          <h3>Таблиця лідерів ({scoreboard.length})</h3>
          {scoreboard.length > 0 ? (
            <ul className="scoreboard-list">
              {scoreboard
                .slice()
                .sort((a, b) => b.score - a.score)
                .map((player, index) => (
                  <li
                    key={player.playerId || player.name}
                    className="scoreboard-item"
                  >
                    <span className="player-rank">#{index + 1}</span>
                    <span className="player-name">{player.name}</span>
                    <span className="player-score">
                      {player.score} балів
                    </span>
                  </li>
                ))}
            </ul>
          ) : (
            <p className="no-players">Очікуємо учасників…</p>
          )}
        </section>
      </div>
    </div>
  );
}

export default QuizHostPlayPage;
