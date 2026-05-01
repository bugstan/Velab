const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function GET() {
  const response = await fetch(`${BACKEND_URL}/api/sessions`, {
    method: "GET",
  });
  const text = await response.text();
  return new Response(text, {
    status: response.status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}
