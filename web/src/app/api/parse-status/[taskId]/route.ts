import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ taskId: string }> }
) {
  const { taskId } = await params;
  const response = await fetch(`${BACKEND_URL}/api/parse/status/${taskId}`, {
    method: "GET",
  });
  const text = await response.text();
  return new Response(text, {
    status: response.status,
    headers: { "Content-Type": "application/json" },
  });
}
