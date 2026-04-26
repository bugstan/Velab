import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  const formData = await request.formData();

  const response = await fetch(`${BACKEND_URL}/api/parse/submit-bundle`, {
    method: "POST",
    body: formData,
  });

  const text = await response.text();
  return new Response(text, {
    status: response.status,
    headers: { "Content-Type": "application/json" },
  });
}
