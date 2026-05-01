import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ bundleId: string }> }
) {
  const { bundleId } = await params;
  const response = await fetch(`${BACKEND_URL}/api/bundles/${bundleId}`, {
    method: "GET",
  });
  const text = await response.text();
  return new Response(text, {
    status: response.status,
    headers: { "Content-Type": "application/json" },
  });
}
