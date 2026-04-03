/**
 * FOTA 诊断平台 — 聊天消息组件
 *
 * 负责渲染单条聊天消息，支持：
 * 1. 用户消息和助手消息的不同样式
 * 2. Markdown 格式渲染（标题、列表、代码块、表格等）
 * 3. Thinking Process 展示（Agent 执行过程）
 * 4. 流式输出动画效果
 * 5. 反馈按钮（点赞/点踩）
 *
 * 设计特点：
 * - 轻量级 Markdown 解析器（无需外部库）
 * - 支持自定义 CSS 变量主题
 * - 流式输出时显示光标动画
 *
 * @author FOTA 诊断平台团队
 * @created 2025
 * @updated 2025
 */

"use client";

import { ChatMessage as ChatMessageType } from "@/lib/types";
import ThinkingProcess from "./ThinkingProcess";
import FeedbackButtons from "./FeedbackButtons";

/**
 * 组件属性接口
 */
interface ChatMessageProps {
  message: ChatMessageType;  // 消息对象，包含角色、内容、思考过程等
}

/**
 * 简易 Markdown 渲染器
 *
 * 将 Markdown 文本转换为 HTML，支持常见的 Markdown 语法：
 * - 标题（## 和 ###）
 * - 分隔线（---）
 * - 粗体（**text**）
 * - 行内代码（`code`）
 * - 链接（[text](url)）
 * - 表格
 * - 代码块（```code```）
 * - 有序列表和无序列表
 *
 * @param content - Markdown 格式的文本
 * @returns HTML 字符串
 */
function renderMarkdown(content: string): string {
  let html = content;

  // 渲染标题
  html = html.replace(/^### (.+)$/gm, '<h3 class="text-sm font-semibold mt-4 mb-2" style="color: var(--text-primary)">$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2 class="text-base font-semibold mt-5 mb-2" style="color: var(--text-primary)">$1</h2>');

  // 渲染分隔线
  html = html.replace(/^---$/gm, '<hr class="my-4" style="border-color: var(--border-light)" />');

  // 渲染行内格式
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');  // 粗体
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');  // 行内代码
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" class="text-blue-400 hover:underline">$1</a>');  // 链接

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
