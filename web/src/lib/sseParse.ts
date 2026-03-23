/**
 * Parse SSE text chunks. Handles \r\n line endings (FastAPI/sse-starlette / HTTP).
 * Returns complete JSON payloads from `data:` lines; keeps incomplete frame in `rest`.
 */
export function parseSSEBuffer(buffer: string): {
  events: unknown[];
  rest: string;
} {
  const normalized = buffer.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const parts = normalized.split("\n\n");
  const rest = parts.pop() ?? "";
  const events: unknown[] = [];

  for (const block of parts) {
    const lines = block.split("\n");
    let dataPayload = "";
    for (const line of lines) {
      if (line.startsWith(":")) continue;
      if (line.startsWith("data:")) {
        dataPayload += line.slice(5).trimStart() + "\n";
      }
    }
    const jsonStr = dataPayload.trimEnd();
    if (!jsonStr) continue;
    try {
      events.push(JSON.parse(jsonStr));
    } catch {
      /* ignore malformed chunk */
    }
  }

  return { events, rest };
}
