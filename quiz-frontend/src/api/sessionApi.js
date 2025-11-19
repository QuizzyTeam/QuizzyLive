import { httpClient } from "./httpClient";

export const sessionApi = {
  // Створити нову ігрову сесію
  create: (quizId) => httpClient.post("/sessions/", { quizId }),
  
  // Отримати інфо про сесію (для відновлення)
  getInfo: (roomCode) => httpClient.get(`/sessions/${roomCode}/info`),
};