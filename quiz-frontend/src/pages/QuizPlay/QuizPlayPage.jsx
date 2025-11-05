import React, { useEffect, useState, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { createQuizSocket } from "../../api/wsClient";
import "./QuizPlayPage.css";

function mapServerPhase(serverPhase) {
  switch (serverPhase) {
    case "LOBBY":
      return "WAITING";
    case "QUESTION_ACTIVE":
      return "QUESTION_ACTIVE";
    case "REVEAL":
      return "REVEAL";
    case "ENDED":
      return "ENDED";
    default:
      return "WAITING";
  }
}

const buildAnswerStorageKey = (quizId) => `quiz_answer_${quizId}`;

function PlayerScoreboard({ scoreboard, playerId, title }) {
  if (!Array.isArray(scoreboard) || scoreboard.length === 0) {
    return null;
  }

  const sorted = [...scoreboard].sort(
    (a, b) => (b.score || 0) - (a.score || 0)
  );

  return (
    <section className="player-scoreboard-section">
      {title && <h3 className="player-scoreboard-title">{title}</h3>}
      <ol className="player-scoreboard-list">
        {sorted.map((player, index) => {
          const isMe =
            playerId && typeof player.playerId === "string"
              ? player.playerId === playerId
              : false;

          return (
            <li
              key={player.playerId || `${player.name}-${index}`}
              className={
                "player-scoreboard-item" + (isMe ? " player-scoreboard-item-me" : "")
              }
            >
              <span className="player-scoreboard-rank">#{index + 1}</span>
              <span className="player-scoreboard-name">{player.name}</span>
              <span className="player-scoreboard-score">
                {player.score ?? 0} балів
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function QuizPlayPage() {
  const navigate = useNavigate();
  const { quizId } = useParams();

  const [ws, setWs] = useState(null);
  const [question, setQuestion] = useState(null);
  const [questionIndex, setQuestionIndex] = useState(-1);
  const [remaining, setRemaining] = useState(0);
  const [selected, setSelected] = useState(null);
  const [phase, setPhase] = useState("CONNECTING");
  const [correctAnswer, setCorrectAnswer] = useState(null);
  const [playerName, setPlayerName] = useState("");
  const [connectionStatus, setConnectionStatus] = useState("connecting");
  const [timeUp, setTimeUp] = useState(false);

  const [scoreboard, setScoreboard] = useState([]);
  const [playerId, setPlayerId] = useState(null);
  const [finalSessionId, setFinalSessionId] = useState(null);

  const timerRef = useRef(null);
  const wsInitialized = useRef(false);

  useEffect(() => {
    if (wsInitialized.current) return;
    wsInitialized.current = true;

    const nameFromStorage =
      window.localStorage.getItem("playerName") || "Player";
    window.localStorage.setItem("playerName", nameFromStorage);
    setPlayerName(nameFromStorage);

    console.log("Підключення учасника:", { name: nameFromStorage, quizId });

    const socket = createQuizSocket({
      role: "player",
      roomCode: quizId,
      name: nameFromStorage,
      onMessage: (msg) => {
        console.log("Player отримав:", msg);

        switch (msg.type) {
          case "state_sync": {
            console.log(
              "State sync від сервера:",
              msg.phase,
              "questionIndex=",
              msg.questionIndex
            );

            const mappedPhase = mapServerPhase(msg.phase);
            setPhase(mappedPhase);
            setConnectionStatus("connected");

            const serverQidx =
              typeof msg.questionIndex === "number" ? msg.questionIndex : -1;

            setQuestionIndex(serverQidx);
            setQuestion(msg.question || null);

            if (typeof msg.playerId === "string" && msg.playerId.length > 0) {
              setPlayerId(msg.playerId);
            }

            if (Array.isArray(msg.scoreboard)) {
              setScoreboard(msg.scoreboard);
            }

            if (timerRef.current) {
              clearInterval(timerRef.current);
            }

            // Відновлюємо відповідь з localStorage, якщо для того ж питання
            const answerKey = buildAnswerStorageKey(quizId);
            let restoredSelected = null;

            try {
              const raw = window.localStorage.getItem(answerKey);
              if (raw) {
                const saved = JSON.parse(raw);
                if (
                  saved &&
                  typeof saved.questionIndex === "number" &&
                  saved.questionIndex === serverQidx &&
                  typeof saved.selectedIndex === "number"
                ) {
                  restoredSelected = saved.selectedIndex;
                } else {
                  window.localStorage.removeItem(answerKey);
                }
              }
            } catch (e) {
              console.warn("Не вдалося відновити збережену відповідь:", e);
            }

            if (
              msg.phase === "QUESTION_ACTIVE" &&
              typeof msg.startedAt === "number" &&
              typeof msg.durationMs === "number"
            ) {
              const now = Date.now();
              const deadline = msg.startedAt + msg.durationMs;
              const diffMs = deadline - now;
              const initialSeconds = Math.max(
                0,
                Math.ceil(diffMs / 1000)
              );

              setRemaining(initialSeconds);
              setTimeUp(initialSeconds <= 0);
              setCorrectAnswer(null);
              setSelected(restoredSelected);

              if (initialSeconds > 0) {
                timerRef.current = setInterval(() => {
                  setRemaining((prev) => {
                    if (prev <= 1) {
                      clearInterval(timerRef.current);
                      setTimeUp(true);
                      return 0;
                    }
                    return prev - 1;
                  });
                }, 1000);
              }
            } else {
              setRemaining(0);
              setTimeUp(false);
              setSelected(restoredSelected);
              setCorrectAnswer(null);
            }

            break;
          }

          case "player_joined": {
            console.log("Успішно приєдналися до вікторини!");
            setConnectionStatus("connected");
            setPhase((prev) =>
              prev === "CONNECTING" ? "WAITING" : prev
            );

            // Оновлюємо локальний leaderboard, щоб усі бачили нових гравців
            setScoreboard((prev) => {
              if (!msg.playerId && !msg.playerName) return prev;

              const exists = prev.find(
                (p) =>
                  p.playerId === msg.playerId || p.name === msg.playerName
              );
              if (exists) return prev;

              return [
                ...prev,
                {
                  playerId: msg.playerId,
                  name: msg.playerName,
                  score: 0,
                },
              ];
            });

            break;
          }

          case "question_started": {
            console.log("Почалось питання:", msg.question);

            const answerKey = buildAnswerStorageKey(quizId);
            try {
              window.localStorage.removeItem(answerKey);
            } catch (e) {
              console.warn(
                "Не вдалося видалити збережену відповідь:",
                e
              );
            }

            setQuestion(msg.question);
            const qidx =
              typeof msg.questionIndex === "number"
                ? msg.questionIndex
                : 0;
            setQuestionIndex(qidx);
            setRemaining(Math.floor(msg.durationMs / 1000));
            setPhase("QUESTION_ACTIVE");
            setSelected(null);
            setCorrectAnswer(null);
            setTimeUp(false);

            if (timerRef.current) {
              clearInterval(timerRef.current);
            }

            timerRef.current = setInterval(() => {
              setRemaining((prev) => {
                if (prev <= 1) {
                  clearInterval(timerRef.current);
                  setTimeUp(true);
                  return 0;
                }
                return prev - 1;
              });
            }, 1000);

            break;
          }

          case "answer_revealed": {
            console.log("Показано відповідь:", msg.correctIndex);
            setPhase("REVEAL");
            setCorrectAnswer(msg.correctIndex);

            if (Array.isArray(msg.scoreboard)) {
              setScoreboard(msg.scoreboard);
            }

            if (timerRef.current) {
              clearInterval(timerRef.current);
            }
            break;
          }

          case "session_ended":
          case "quiz_ended": {
            console.log("Сесія завершена, показуємо фінальний лідерборд");

            if (timerRef.current) {
              clearInterval(timerRef.current);
            }

            try {
              window.localStorage.removeItem(
                buildAnswerStorageKey(quizId)
              );
            } catch (e) {
              console.warn(
                "Не вдалося очистити відповідь при завершенні:",
                e
              );
            }

            setPhase("ENDED");
            setRemaining(0);
            setTimeUp(false);
            setCorrectAnswer(null);
            setQuestion(null);
            setSelected(null);
            setConnectionStatus("connected");

            if (Array.isArray(msg.scoreboard)) {
              setScoreboard(msg.scoreboard);
            }

            if (typeof msg.sessionId === "string") {
              setFinalSessionId(msg.sessionId);
            }

            break;
          }

          case "error": {
            console.error("Помилка від сервера:", msg.message);
            alert(`Помилка: ${msg.message}`);
            setConnectionStatus("error");

            if (
              msg.message?.includes("not found") ||
              msg.message?.includes("does not exist") ||
              msg.message?.includes("не знайдена")
            ) {
              setTimeout(() => navigate("/join"), 2000);
            }
            break;
          }

          default: {
            console.log("Невідомий тип повідомлення:", msg.type);
          }
        }
      },
    });

    socket.onopen = () => {
      console.log("WebSocket підключено як player");
      setConnectionStatus("connected");
    };

    socket.onclose = (event) => {
      console.log("WebSocket закрито:", event);
      setConnectionStatus("disconnected");
      wsInitialized.current = false;
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };

    socket.onerror = (error) => {
      console.error("WebSocket помилка:", error);
      setConnectionStatus("error");
    };

    setWs(socket);

    return () => {
      console.log("Очищення WebSocket з'єднання");
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
      if (socket.readyState === WebSocket.OPEN) {
        socket.close();
      }
      wsInitialized.current = false;
    };
  }, [quizId, navigate]);

  const handleAnswer = (idx) => {
    if (timeUp || remaining <= 0) {
      console.log("Час вийшов, відповідь не приймається");
      return;
    }

    if (selected !== null || phase !== "QUESTION_ACTIVE") {
      console.log("Відповідь вже надіслана або питання неактивне");
      return;
    }

    console.log("Надсилаємо відповідь:", {
      optionIndex: idx,
      questionIndex: questionIndex,
    });

    setSelected(idx);

    try {
      const answerKey = buildAnswerStorageKey(quizId);
      const payload = {
        questionIndex: questionIndex,
        selectedIndex: idx,
      };
      window.localStorage.setItem(answerKey, JSON.stringify(payload));
    } catch (e) {
      console.warn("Не вдалося зберегти відповідь у localStorage:", e);
    }

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.sendJson({
        type: "player:answer",
        questionIndex: questionIndex,
        optionIndex: idx,
      });
    } else {
      console.error("WebSocket не підключено!");
    }
  };

  // СТАН: підключення
  if (connectionStatus === "connecting" || phase === "CONNECTING") {
    return (
      <div className="quiz-play-page">
        <div className="status-box">
          <h2>Підключення до вікторини...</h2>
          <p>Код: {quizId}</p>
          <p>Ім&apos;я: {playerName}</p>
        </div>
      </div>
    );
  }

  // СТАН: помилка
  if (connectionStatus === "error") {
    return (
      <div className="quiz-play-page">
        <div className="status-box error">
          <h2>Помилка підключення</h2>
          <p>Не вдалося підключитися до вікторини.</p>
          <p>Перевірте код вікторини та спробуйте ще раз.</p>
          <button onClick={() => navigate("/join")}>Повернутись</button>
        </div>
      </div>
    );
  }

  // СТАН: відключено
  if (connectionStatus === "disconnected") {
    return (
      <div className="quiz-play-page">
        <div className="status-box">
          <h2>З&apos;єднання втрачено</h2>
          <p>Зв&apos;язок з сервером перервано.</p>
          <button onClick={() => window.location.reload()}>
            Перепідключитись
          </button>
          <button onClick={() => navigate("/join")}>Повернутись</button>
        </div>
      </div>
    );
  }

  // ФІНАЛЬНИЙ ЕКРАН: тільки лідерборд + кнопка "На головну"
  if (phase === "ENDED") {
    return (
      <div className="quiz-play-page">
        <header className="player-header">
          <div className="player-name">Гравець: {playerName}</div>
          <div className="connection-status">
            {connectionStatus === "connected" ? "Підключено" : "Відключено"}
          </div>
        </header>

        <div className="player-final-wrapper">
          <h2 className="player-final-title">Вікторина завершена</h2>
          {finalSessionId && (
            <p className="player-final-subtitle">
              ID сесії: {finalSessionId}
            </p>
          )}

          <PlayerScoreboard
            scoreboard={scoreboard}
            playerId={playerId}
            title="Підсумкова таблиця лідерів"
          />

          {(!scoreboard || scoreboard.length === 0) && (
            <p className="player-scoreboard-empty">
              Поки що немає даних про учасників.
            </p>
          )}

          <button
            className="player-scoreboard-home-btn"
            onClick={() => navigate("/")}
          >
            Повернутися на головну
          </button>
        </div>
      </div>
    );
  }

  const isUrgent = remaining <= 5 && remaining > 0;

  return (
    <div className="quiz-play-page">
      <header className="player-header">
        <div className="player-name">Гравець: {playerName}</div>
        <div className="connection-status">
          {connectionStatus === "connected" ? "Підключено" : "Відключено"}
        </div>
      </header>

      {phase === "WAITING" && (
        <div className="waiting-box">
          <h2>Очікуємо початку вікторини...</h2>
          <p>Ведучий почне гру незабаром.</p>
          <div className="pulse-indicator">●</div>
        </div>
      )}

      {phase === "QUESTION_ACTIVE" && question && (
        <div className="question-box">
          <div className="question-header">
            <h3>Питання {question.position + 1}</h3>
            <div className={`timer ${isUrgent ? "urgent" : ""}`}>
              {remaining} с
            </div>
          </div>
          <div className="question-text">{question.question_text}</div>

          <div className="answers-grid">
            {question.answers.map((ans, i) => (
              <button
                key={i}
                onClick={() => handleAnswer(i)}
                disabled={
                  selected !== null || timeUp || remaining <= 0
                }
                className={
                  "answer-btn" + (selected === i ? " selected" : "")
                }
              >
                <span className="answer-number">{i + 1}</span>
                <span className="answer-text">{ans}</span>
              </button>
            ))}
          </div>

          {selected !== null && !timeUp && (
            <div className="answer-submitted">Відповідь надіслано!</div>
          )}

          {timeUp && selected === null && (
            <div className="answer-submitted time-up-message">
              Час вийшов. Відповідь не була надіслана.
            </div>
          )}
        </div>
      )}

      {phase === "REVEAL" && question && (
        <div className="reveal-box">
          <h2>Результати</h2>
          <p className="question-text">{question.question_text}</p>

          {question.answers.map((ans, i) => {
            const isCorrect = i === correctAnswer;
            const isSelected = i === selected;
            const classes = [
              "answer-result",
              isCorrect ? "correct" : "",
              isSelected ? "selected" : "",
            ]
              .filter(Boolean)
              .join(" ");

            return (
              <div key={i} className={classes}>
                <span className="answer-number">{i + 1}</span>
                <span className="answer-text">{ans}</span>
                {isCorrect && <span className="check">✓</span>}
                {isSelected && !isCorrect && (
                  <span className="cross">✗</span>
                )}
              </div>
            );
          })}

          {selected === correctAnswer && selected !== null && (
            <div className="result-message success">
              Правильно! +100 балів
            </div>
          )}

          {selected !== correctAnswer && selected !== null && (
            <div className="result-message wrong">
              Неправильно. Правильна відповідь: {correctAnswer + 1}
            </div>
          )}

          {selected === null && (
            <div className="result-message missed">Час вийшов!</div>
          )}

          <div className="waiting-next">
            Очікуємо наступного питання...
          </div>
        </div>
      )}

      {phase !== "WAITING" && (
        <PlayerScoreboard
          scoreboard={scoreboard}
          playerId={playerId}
          title="Таблиця лідерів"
        />
      )}
    </div>
  );
}

export default QuizPlayPage;
