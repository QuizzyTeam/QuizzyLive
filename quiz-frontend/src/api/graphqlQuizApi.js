// src/api/graphqlQuizApi.js
import { graphqlRequest } from "./graphqlClient";

export async function getQuizInfo(quizId) {
  const query = `
    query GetQuizInfo($id: String!) {
      quizInfo(id: $id) {
        id
        title
        description
        createdAt
        updatedAt
        questionCount
        rating
      }
    }
  `;

  const variables = { id: quizId };

  const data = await graphqlRequest(query, variables);
  return data.quizInfo;
}
