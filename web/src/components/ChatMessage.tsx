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

import { useState } from "react";
import { ChatMessage as ChatMessageType } from "@/lib/types";
import {
  BundleStatusPayload,
  formatBundleStatusDetails,
  getBundleQueryErrorText,
} from "@/lib/bundleStatus";
import ThinkingProcess from "./ThinkingProcess";
import FeedbackButtons from "./FeedbackButtons";
import SourcePanel from "./SourcePanel";
import UploadSummaryCard from "./UploadSummaryCard";

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
  // First, handle block-level replacements that need to preserve structure
  let html = content;

  // 渲染THINKING标记内容（在其他渲染之前）
  html = html.replace(/<<<THINKING>>>([\s\S]*?)<<<\/THINKING>>>/g, (_match, thinkingContent) => {
    return `<details class="my-3 rounded-lg overflow-hidden" style="border: 1px solid var(--border-color); background: var(--bg-tertiary)">
      <summary class="px-4 py-2.5 cursor-pointer text-xs font-medium flex items-center gap-2 hover:opacity-80 transition-opacity" style="color: var(--text-muted)">
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" class="transform transition-transform">
          <path d="M3 4.5L6 7.5L9 4.5" />
        </svg>
        <span>思考过程</span>
      </summary>
      <div class="px-4 py-3 text-xs leading-relaxed whitespace-pre-wrap" style="color: var(--text-muted); border-top: 1px solid var(--border-color)">${thinkingContent.trim()}</div>
    </details>`;
  });

  // 渲染代码块（在split之前处理，避免被拆分）
  html = html.replace(/```([\s\S]*?)```/g, (_match, code) => {
    return `<pre class="my-3 p-3 rounded-lg text-xs overflow-x-auto" style="background: var(--bg-tertiary); color: var(--text-secondary)"><code>${code.trim()}</code></pre>`;
  });

  // Now process line by line
  const lines = html.split("\n");
  let inList = false;
  let listType: "ul" | "ol" = "ul";
  const processed: string[] = [];
  let paragraphBuffer: string[] = [];

  const flushParagraph = () => {
    if (paragraphBuffer.length > 0) {
      let paragraphText = paragraphBuffer.join(" ").trim();
      if (paragraphText) {
        // Apply inline formatting to the paragraph text
        paragraphText = paragraphText.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        paragraphText = paragraphText.replace(/`([^`]+)`/g, '<code>$1</code>');
        paragraphText = paragraphText.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" class="text-blue-400 hover:underline">$1</a>');
        paragraphText = paragraphText.replace(/置信度[：:]\s*(高|中|低|high|medium|low)/gi, (match, level) => {
          const normalizedLevel = level.toLowerCase();
          let color, bgColor, text;
          if (normalizedLevel === '高' || normalizedLevel === 'high') {
            color = '#238636';
            bgColor = 'rgba(35, 134, 54, 0.1)';
            text = '高';
          } else if (normalizedLevel === '中' || normalizedLevel === 'medium') {
            color = '#d29922';
            bgColor = 'rgba(210, 153, 34, 0.1)';
            text = '中';
          } else {
            color = '#f85149';
            bgColor = 'rgba(248, 81, 73, 0.1)';
            text = '低';
          }
          return `<span class="inline-flex items-center gap-1 text-xs"><span style="color: var(--text-secondary)">置信度:</span><span class="px-2 py-0.5 rounded font-medium" style="color: ${color}; background: ${bgColor}">${text}</span></span>`;
        });
        
        processed.push(`<p class="text-sm leading-relaxed mb-1">${paragraphText}</p>`);
      }
      paragraphBuffer = [];
    }
  };

  for (const line of lines) {
    const trimmedLine = line.trim();
    
    // Skip empty lines
    if (!trimmedLine) {
      if (paragraphBuffer.length > 0) {
        flushParagraph();
      }
      continue;
    }

    // Check for headings
    const h3Match = trimmedLine.match(/^### (.+)$/);
    const h2Match = trimmedLine.match(/^## (.+)$/);
    if (h3Match) {
      flushParagraph();
      if (inList) {
        processed.push(listType === "ul" ? "</ul>" : "</ol>");
        inList = false;
      }
      processed.push(`<h3 class="text-sm font-semibold mt-4 mb-2" style="color: var(--text-primary)">${h3Match[1]}</h3>`);
      continue;
    }
    if (h2Match) {
      flushParagraph();
      if (inList) {
        processed.push(listType === "ul" ? "</ul>" : "</ol>");
        inList = false;
      }
      processed.push(`<h2 class="text-base font-semibold mt-5 mb-2" style="color: var(--text-primary)">${h2Match[1]}</h2>`);
      continue;
    }

    // Check for horizontal rule
    if (trimmedLine === '---') {
      flushParagraph();
      if (inList) {
        processed.push(listType === "ul" ? "</ul>" : "</ol>");
        inList = false;
      }
      processed.push('<hr class="my-4" style="border-color: var(--border-light)" />');
      continue;
    }

    // Check for lists
    const ulMatch = trimmedLine.match(/^- (.+)$/);
    const olMatch = trimmedLine.match(/^(\d+)\. (.+)$/);
    
    if (ulMatch) {
      flushParagraph();
      if (!inList || listType !== "ul") {
        if (inList) processed.push(listType === "ul" ? "</ul>" : "</ol>");
        processed.push('<ul class="list-disc ml-5 my-2 space-y-1">');
        inList = true;
        listType = "ul";
      }
      processed.push(`<li class="text-sm leading-relaxed">${ulMatch[1]}</li>`);
      continue;
    }
    
    if (olMatch) {
      flushParagraph();
      if (!inList || listType !== "ol") {
        if (inList) processed.push(listType === "ul" ? "</ul>" : "</ol>");
        processed.push('<ol class="list-decimal ml-5 my-2 space-y-1">');
        inList = true;
        listType = "ol";
      }
      processed.push(`<li class="text-sm leading-relaxed">${olMatch[2]}</li>`);
      continue;
    }

    // Check for tables
    const tableMatch = trimmedLine.match(/^(\| .+)$/);
    if (tableMatch) {
      flushParagraph();
      if (inList) {
        processed.push(listType === "ul" ? "</ul>" : "</ol>");
        inList = false;
      }
      if (!trimmedLine.match(/^\|\s*[-:]+/)) {
        const cells = trimmedLine.split("|").filter(Boolean).map((c) => c.trim());
        const row = cells.map((c) => `<td class="px-3 py-1.5 text-xs" style="border: 1px solid var(--border-color)">${c}</td>`).join("");
        processed.push(`<table class="w-full my-3 text-xs" style="border-collapse: collapse; border: 1px solid var(--border-color)"><tr>${row}</tr></table>`);
      }
      continue;
    }

    // Check if line is already an HTML tag (from previous replacements)
    if (trimmedLine.startsWith("<")) {
      flushParagraph();
      if (inList) {
        processed.push(listType === "ul" ? "</ul>" : "</ol>");
        inList = false;
      }
      processed.push(line);
      continue;
    }

    // Regular text - add to paragraph buffer
    if (inList) {
      processed.push(listType === "ul" ? "</ul>" : "</ol>");
      inList = false;
    }
    paragraphBuffer.push(trimmedLine);
  }
  
  // Flush any remaining paragraph
  flushParagraph();
  
  if (inList) {
    processed.push(listType === "ul" ? "</ul>" : "</ol>");
  }

  return processed.join("\n");
}

export default function ChatMessageComponent({ message }: ChatMessageProps) {
  const [statusByBundleId, setStatusByBundleId] = useState<Record<string, string>>({});
  const [loadingBundleId, setLoadingBundleId] = useState<string | null>(null);

  const fetchBundleStatus = async (bundleId: string) => {
    setLoadingBundleId(bundleId);
    try {
      const resp = await fetch(`/api/bundle-status/${encodeURIComponent(bundleId)}`);
      const payload = (await resp.json()) as BundleStatusPayload;
      if (!resp.ok) {
        setStatusByBundleId((prev) => ({
          ...prev,
          [bundleId]: getBundleQueryErrorText(payload, resp.status),
        }));
        return;
      }
      setStatusByBundleId((prev) => ({
        ...prev,
        [bundleId]: formatBundleStatusDetails(payload) || "已查询，返回为空",
      }));
    } catch (err) {
      setStatusByBundleId((prev) => ({
        ...prev,
        [bundleId]: `网络错误: ${(err as Error).message}`,
      }));
    } finally {
      setLoadingBundleId((current) => (current === bundleId ? null : current));
    }
  };

  const renderBundleActions = () => {
    if (message.isStreaming || !message.bundleActions || message.bundleActions.length === 0) {
      return null;
    }
    return (
      <div className="mt-3 flex flex-wrap gap-2">
        {message.bundleActions.map((action) => (
          <button
            key={`${action.bundleId}-${action.label}-${action.action ?? "status"}`}
            type="button"
            onClick={() => {
              if (action.action === "rangeQuery") {
                window.open(
                  `/temp/range-query?bundle_id=${encodeURIComponent(action.bundleId)}`,
                  "_blank"
                );
                return;
              }
              void fetchBundleStatus(action.bundleId);
            }}
            className="text-xs px-3 py-1.5 rounded-lg font-medium transition-opacity hover:opacity-90"
            style={{
              background: "var(--accent-blue)",
              color: "#fff",
              border: "none",
              cursor: "pointer",
            }}
          >
            {action.action === "rangeQuery"
              ? `打开「${action.label}」临时查询页`
              : loadingBundleId === action.bundleId
                ? `查询「${action.label}」状态中...`
                : `查看「${action.label}」摄取状态`}
          </button>
        ))}
      </div>
    );
  };

  const renderStatusDetails = () => {
    const entries = Object.entries(statusByBundleId);
    if (entries.length === 0) return null;
    return (
      <div className="mt-3 grid gap-2">
        {entries.map(([bundleId, details]) => (
          <pre
            key={bundleId}
            className="rounded-lg border px-3 py-2 text-xs whitespace-pre-wrap"
            style={{
              borderColor: "var(--border-color)",
              color: "var(--text-primary)",
              background: "var(--bg-secondary)",
            }}
          >
            {`bundle_id: ${bundleId}\n${details}`}
          </pre>
        ))}
      </div>
    );
  };

  const renderUploadProgress = () => {
    if (!message.uploadProgress) return null;
    const progress = message.uploadProgress;
    const stripFileNamePrefix = (value: string): string => {
      const normalized = value.trim();
      if (!normalized) return "处理中...";
      for (const file of progress.files) {
        const prefix = `${file.fileName} - `;
        if (normalized.startsWith(prefix)) {
          return normalized.slice(prefix.length).trim() || "处理中...";
        }
      }
      return normalized;
    };
    const mainStatusText = stripFileNamePrefix(progress.message || "处理中...");
    const hasFailed = progress.files.some((file) => file.status === "failed");
    const allCompleted = progress.files.length > 0 && progress.files.every((file) => file.status === "completed");
    const progressBarColor = hasFailed
      ? "#f85149"
      : allCompleted
        ? "#238636"
        : "var(--accent-blue)";
    return (
      <div
        className="mt-3 rounded-xl border p-3"
        style={{ borderColor: "var(--border-color)", background: "var(--bg-secondary)" }}
      >
        <div className="flex items-center justify-between text-xs mb-1">
          <span className="truncate pr-2" style={{ color: "var(--text-secondary)" }} title={mainStatusText}>
            {mainStatusText}
          </span>
          <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>
            {Math.max(0, Math.min(100, progress.percent))}%
          </span>
        </div>
        <div className="h-1.5 rounded-full mb-2" style={{ background: "var(--border-color)" }}>
          <div
            className="h-1.5 rounded-full transition-all"
            style={{
              width: `${Math.max(0, Math.min(100, progress.percent))}%`,
              background: progressBarColor,
            }}
          />
        </div>
      </div>
    );
  };

  if (message.role === "system") {
    return (
      <div className="mb-6 animate-fade-in">
        <div
          className="rounded-xl border px-4 py-3"
          style={{
            borderColor: "var(--border-color)",
            background: "var(--bg-secondary)",
          }}
        >
          <div className="mb-2 text-xs font-semibold" style={{ color: "var(--text-secondary)" }}>
            系统反馈
          </div>
          {message.content ? (
            <div className="text-sm" style={{ color: "var(--text-primary)" }}>
              {message.content}
            </div>
          ) : null}
          {!message.isStreaming && message.uploadSummaries && message.uploadSummaries.length > 0 && (
            <div className="mt-3 grid gap-3">
              {message.uploadSummaries.map((summary) => (
                <UploadSummaryCard key={`${summary.bundleId}-${summary.fileName}`} summary={summary} />
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

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
          <div className="whitespace-pre-wrap">{message.content}</div>
          {renderUploadProgress()}
          {renderBundleActions()}
          {renderStatusDetails()}
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

          {renderBundleActions()}
          {renderStatusDetails()}

          {!message.isStreaming && message.sources && message.sources.length > 0 && (
            <SourcePanel sources={message.sources} />
          )}

          {!message.isStreaming && message.content && <FeedbackButtons />}
        </div>
      </div>
    </div>
  );
}
