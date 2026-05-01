import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ bundleId: string }> }
) {
  const { bundleId } = await params;
  const query = request.nextUrl.searchParams.toString();
  const upstreamUrl = `${BACKEND_URL}/api/bundles/${bundleId}/logs${query ? `?${query}` : ""}`;
  const response = await fetch(upstreamUrl, { method: "GET" });
  const text = await response.text();

  return new Response(text, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("content-type") || "application/x-ndjson; charset=utf-8",
      "X-Truncated": response.headers.get("x-truncated") || "false",
      "X-Estimated-Lines": response.headers.get("x-estimated-lines") || "0",
    },
  });
}
