"use client";

import { ChatMessage as ChatMessageType } from "@/lib/types";
import ThinkingProcess from "./ThinkingProcess";
import FeedbackButtons from "./FeedbackButtons";

interface ChatMessageProps {
  message: ChatMessageType;
}

function renderMarkdown(content: string): string {
  let html = content;

  html = html.replace(/^### (.+)$/gm, '<h3 class="text-sm font-semibold mt-4 mb-2" style="color: var(--text-primary)">$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2 class="text-base font-semibold mt-5 mb-2" style="color: var(--text-primary)">$1</h2>');

  html = html.replace(/^---$/gm, '<hr class="my-4" style="border-color: var(--border-light)" />');

  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" class="text-blue-400 hover:underline">$1</a>');

  html = html.replace(/^(\| .+)$/gm, (match) => {
    if (match.match(/^\|\s*[-:]+/)) return "";
    const cells = match.split("|").filter(Boolean).map((c) => c.trim());
    const row = cells.map((c) => `<td class="px-3 py-1.5 text-xs" style="border: 1px solid var(--border-color)">${c}</td>`).join("");
    return `<tr>${row}</tr>`;
  });

  html = html.replace(
    /(<tr>[\s\S]*?<\/tr>[\s]*)+/g,
    (match) =>
      `<table class="w-full my-3 text-xs" style="border-collapse: collapse; border: 1px solid var(--border-color)">${match}</table>`
  );

  html = html.replace(/```([\s\S]*?)```/g, (_match, code) => {
    return `<pre class="my-3 p-3 rounded-lg text-xs overflow-x-auto" style="background: var(--bg-tertiary); color: var(--text-secondary)"><code>${code.trim()}</code></pre>`;
  });

  const lines = html.split("\n");
  let inList = false;
  let listType: "ul" | "ol" = "ul";
  const processed: string[] = [];

  for (const line of lines) {
    const ulMatch = line.match(/^- (.+)$/);
    const olMatch = line.match(/^(\d+)\. (.+)$/);

    if (ulMatch) {
      if (!inList || listType !== "ul") {
        if (inList) processed.push(listType === "ul" ? "</ul>" : "</ol>");
        processed.push('<ul class="list-disc ml-5 my-2 space-y-1">');
        inList = true;
        listType = "ul";
      }
      processed.push(`<li class="text-sm leading-relaxed">${ulMatch[1]}</li>`);
    } else if (olMatch) {
      if (!inList || listType !== "ol") {
        if (inList) processed.push(listType === "ul" ? "</ul>" : "</ol>");
        processed.push('<ol class="list-decimal ml-5 my-2 space-y-1">');
        inList = true;
        listType = "ol";
      }
      processed.push(`<li class="text-sm leading-relaxed">${olMatch[2]}</li>`);
    } else {
      if (inList) {
        processed.push(listType === "ul" ? "</ul>" : "</ol>");
        inList = false;
      }
      if (line.trim() && !line.startsWith("<")) {
        processed.push(`<p class="text-sm leading-relaxed mb-1">${line}</p>`);
      } else {
        processed.push(line);
      }
    }
  }
  if (inList) {
    processed.push(listType === "ul" ? "</ul>" : "</ol>");
  }

  return processed.join("\n");
}

export default function ChatMessageComponent({ message }: ChatMessageProps) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end mb-6 animate-fade-in">
        <div
          className="max-w-2xl px-4 py-3 rounded-2xl text-sm"
          style={{
            background: "var(--bg-tertiary)",
            color: "var(--text-primary)",
            border: "1px solid var(--border-color)",
          }}
        >
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="mb-6 animate-fade-in">
      <div className="flex items-start gap-3">
        <div
          className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5"
          style={{ background: "var(--accent-red)" }}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="white"
            strokeWidth="2"
          >
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
            <circle cx="12" cy="7" r="4" />
          </svg>
        </div>

        <div className="flex-1 min-w-0">
          <div
            className="text-xs font-semibold mb-2"
            style={{ color: "var(--text-secondary)" }}
          >
            Technician
          </div>

          {message.thinking && (
            <ThinkingProcess
              steps={message.thinking.steps}
              defaultExpanded={message.thinking.isExpanded}
            />
          )}

          <div
            className={`markdown-content ${message.isStreaming ? "streaming-cursor" : ""}`}
            dangerouslySetInnerHTML={{
              __html: renderMarkdown(message.content),
            }}
          />

          {!message.isStreaming && message.content && <FeedbackButtons />}
        </div>
      </div>
    </div>
  );
}
