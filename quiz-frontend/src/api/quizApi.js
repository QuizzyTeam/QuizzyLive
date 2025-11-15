import { httpClient } from "./httpClient";

export const quizApi = {
  list: () => httpClient.get("/quizzes/"),
  getById: (id) => httpClient.get(`/quizzes/${id}`),
  create: (payload) => httpClient.post("/quizzes/", payload),
  update: (id, payload) => httpClient.put(`/quizzes/${id}`, payload),
  remove: (id) => httpClient.delete(`/quizzes/${id}`),

  startRoom: (quizId) =>
    httpClient.post(`/quizzes/${quizId}/room-code`, {}),

  resolveRoomCode: (roomCode) =>
    httpClient.get(`/quizzes/room-code/${roomCode}/resolve`),
};