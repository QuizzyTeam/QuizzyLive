// graphqlClient.js
const GRAPHQL_URL = import.meta.env.VITE_GRAPHQL_URL;

export async function graphqlRequest(query, variables = {}) {
  const response = await fetch(GRAPHQL_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, variables }),
  });

  const body = await response.json();

  if (body.errors) {
    console.error("GraphQL errors:", body.errors);
    throw new Error(body.errors[0].message);
  }

  return body.data;
}
