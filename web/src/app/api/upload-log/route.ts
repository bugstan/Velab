import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  const formData = await request.formData();

  // log_pipeline expects multipart with field name "file"; case_id is no longer used.
  const upstream = new FormData();
  const file = formData.get("file");
  if (file) upstream.append("file", file);

  const response = await fetch(`${BACKEND_URL}/api/bundles`, {
    method: "POST",
    body: upstream,
  });

  const text = await response.text();
  return new Response(text, {
    status: response.status,
    headers: { "Content-Type": "application/json" },
  });
}
