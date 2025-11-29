import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { quizApi } from "../../api/quizApi";
import { sessionApi } from "../../api/sessionApi";
import "./CreateQuizPage.css";

function CreateQuizPage() {
  const navigate = useNavigate();

  const [quizTitle, setQuizTitle] = useState("");
  const [quizDescription, setQuizDescription] = useState("");

  const [questions, setQuestions] = useState([
    { questionText: "", answers: ["", "", "", ""], correctAnswer: null }
  ]);

  const [isEditing, setIsEditing] = useState(false);
  const [editingQuizId, setEditingQuizId] = useState(null);

  const [archive, setArchive] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Info modal
  const [infoModalOpen, setInfoModalOpen] = useState(false);
  const [selectedQuizInfo, setSelectedQuizInfo] = useState(null);

  const handleStartSession = async (quizId) => {
    setLoading(true);
    try {
      const { roomCode } = await sessionApi.create(quizId);
      navigate(`/lobby/${roomCode}`);
    } catch (err) {
      alert("Не вдалося створити сесію: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  const resetToCreateMode = () => {
    setIsEditing(false);
    setEditingQuizId(null);
    setQuizTitle("");
    setQuizDescription("");
    setQuestions([{ questionText: "", answers: ["", "", "", ""], correctAnswer: null }]);
  };

  const validateQuiz = (title, qs) => {
    if (!title.trim()) {
      alert("Введіть назву!");
      return false;
    }
    if (!qs.length) {
      alert("Додайте питання!");
      return false;
    }
    for (let i = 0; i < qs.length; i++) {
      if (!qs[i].questionText.trim()) {
        alert(`Питання ${i + 1} пусте`);
        return false;
      }
      if (qs[i].answers.some(a => !a.trim())) {
        alert(`Питання ${i + 1} має пусті відповіді`);
        return false;
      }
      if (qs[i].correctAnswer === null) {
        alert(`Питання ${i + 1} без правильної відповіді`);
        return false;
      }
    }
    return true;
  };

  const fetchArchive = async () => {
    setLoading(true);
    try {
      setArchive(await quizApi.list());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchQuizAndEdit = async (id) => {
    setLoading(true);
    try {
      const data = await quizApi.getById(id);
      setIsEditing(true);
      setEditingQuizId(id);

      setQuizTitle(data.title);
      setQuizDescription(data.description || "");

      setQuestions(
        data.questions.map(qq => ({
          questionText: qq.questionText,
          answers: [...qq.answers],
          correctAnswer: qq.correctAnswer
        }))
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const createQuiz = async () => {
    if (!validateQuiz(quizTitle, questions)) return;

    setLoading(true);
    try {
      await quizApi.create({
        title: quizTitle.trim(),
        description: quizDescription.trim(),
        questions
      });
      await fetchArchive();
      alert("Збережено!");
      resetToCreateMode();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const updateQuiz = async () => {
    if (!validateQuiz(quizTitle, questions)) return;

    setLoading(true);
    try {
      await quizApi.update(editingQuizId, {
        title: quizTitle.trim(),
        description: quizDescription.trim(),
        questions
      });
      await fetchArchive();
      alert("Оновлено!");
      resetToCreateMode();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const deleteQuiz = async (id) => {
    if (!window.confirm("Видалити?")) return;
    setLoading(true);
    try {
      await quizApi.remove(id);
      await fetchArchive();
      if (isEditing && editingQuizId === id) resetToCreateMode();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchArchive();
  }, []);

  const handleAddQuestion = () =>
    setQuestions(prev => [...prev, { questionText: "", answers: ["", "", "", ""], correctAnswer: null }]);

  const handleRemoveQuestion = (idx) =>
    setQuestions(prev => prev.length > 1 ? prev.filter((_, i) => i !== idx) : prev);

  const handleQuestionChange = (idx, val) =>
    setQuestions(prev => {
      const upd = [...prev];
      upd[idx].questionText = val;
      return upd;
    });

  const handleAnswerChange = (qIdx, aIdx, val) =>
    setQuestions(prev => {
      const upd = [...prev];
      upd[qIdx].answers[aIdx] = val;
      return upd;
    });

  const handleSetCorrectAnswer = (qIdx, aIdx) =>
    setQuestions(prev => {
      const upd = [...prev];
      upd[qIdx].correctAnswer = aIdx;
      return upd;
    });

  // ============================
  // ВІКНО ІНФОРМАЦІЇ ПРО ВІКТОРИНУ
  // ============================

  const openInfoModal = async (quizId) => {
    setLoading(true);
    try {
      const data = await quizApi.getById(quizId);
      setSelectedQuizInfo(data);
      setInfoModalOpen(true);
    } catch (err) {
      alert("Не вдалося завантажити інформацію");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="create-quiz-container two-columns">
      <div className="logo" onClick={() => navigate("/")}>
        <span className="logo-text">QuizzyLive</span>
      </div>

      {/* ================= ЛІВА ПАНЕЛЬ ================= */}
      <div className="left-pane">
        <button className="cancel-btn" onClick={() => navigate("/")}>✖ Скасувати</button>

        <div className="quiz-form">
          <h2>{isEditing ? "Редагування" : "Створення"}</h2>

          {error && <div className="error-box">{error}</div>}
          {loading && <div className="loading-box">Завантаження...</div>}

          <input
            type="text"
            placeholder="Назва вікторини"
            value={quizTitle}
            onChange={(e) => setQuizTitle(e.target.value)}
            className="quiz-title-input"
          />

          {/* ОПИС */}
          <textarea
            placeholder="Опис вікторини"
            value={quizDescription}
            onChange={(e) => setQuizDescription(e.target.value)}
            className="quiz-description-input"
          />

          {/* ПИТАННЯ */}
          {questions.map((q, qIndex) => (
            <div key={qIndex} className="question-block">
              <div className="question-header">
                <h3>Питання {qIndex + 1}</h3>
                <button className="remove-question-btn" onClick={() => handleRemoveQuestion(qIndex)}>🗑 Видалити</button>
              </div>

              <input
                type="text"
                placeholder="Текст питання"
                value={q.questionText}
                onChange={(e) => handleQuestionChange(qIndex, e.target.value)}
                className="question-input"
              />

              <div className="answers-container">
                {q.answers.map((ans, aIndex) => (
                  <div key={aIndex} className="answer-option">
                    <input
                      type="text"
                      placeholder={`Відповідь ${aIndex + 1}`}
                      value={ans}
                      onChange={(e) => handleAnswerChange(qIndex, aIndex, e.target.value)}
                      className="answer-input"
                    />
                    <label>
                      <input
                        type="radio"
                        name={`correct-${qIndex}`}
                        checked={q.correctAnswer === aIndex}
                        onChange={() => handleSetCorrectAnswer(qIndex, aIndex)}
                      />
                      Правильна
                    </label>
                  </div>
                ))}
              </div>
            </div>
          ))}

          <div className="form-actions">
            <button className="add-question-btn" onClick={handleAddQuestion}>➕ Додати питання</button>

            {!isEditing ? (
              <button className="save-quiz-btn" onClick={createQuiz}>💾 Зберегти</button>
            ) : (
              <>
                <button className="save-quiz-btn" onClick={updateQuiz}>🔄 Оновити</button>
                <button className="secondary-btn" onClick={resetToCreateMode}>↩ Лишити як є</button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* ================= ПРАВА ПАНЕЛЬ ================= */}
      <div className="right-pane">
        <div className="archive-header">
          <h2>Архів</h2>
          <button className="refresh-btn" onClick={fetchArchive} disabled={loading}>⟳</button>
        </div>

        {archive.length === 0 ? (
          <p className="archive-empty">Порожньо</p>
        ) : (
          <ul className="archive-list">
            {archive.map(q => (
              <li key={q.id} className="archive-item">
                <span className="archive-title">{q.title}</span>

                <div className="archive-actions">
                  <button className="start-btn" onClick={() => handleStartSession(q.id)} disabled={loading}>🎮</button>
                  <button className="info-btn" onClick={() => openInfoModal(q.id)}>ℹ</button>
                  <button className="edit-btn" onClick={() => fetchQuizAndEdit(q.id)}>✏</button>
                  <button className="delete-btn" onClick={() => deleteQuiz(q.id)}>🗑</button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* ================= МОДАЛЬНЕ ВІКНО ІНФОРМАЦІЇ ================= */}
      {infoModalOpen && selectedQuizInfo && (
        <div className="info-modal-backdrop" onClick={() => setInfoModalOpen(false)}>
          <div className="info-modal" onClick={(e) => e.stopPropagation()}>
            <h2>{selectedQuizInfo.title}</h2>

            <p><strong>Дата створення:</strong> {new Date(selectedQuizInfo.createdAt).toLocaleString()}</p>
            <p><strong>Дата оновлення:</strong> {new Date(selectedQuizInfo.updatedAt).toLocaleString()}</p>
            <p><strong>Кількість питань:</strong> {selectedQuizInfo.questions?.length}</p>

            <p><strong>Опис:</strong></p>
            <p className="modal-description">{selectedQuizInfo.description || "—"}</p>

            <p><strong>Рейтинг:</strong> {selectedQuizInfo.rating || 0}</p>

            <button className="close-modal-btn" onClick={() => setInfoModalOpen(false)}>
              Закрити
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default CreateQuizPage;
