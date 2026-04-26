"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const LS_KEY = "fota_last_parse_task_id";

/** 从聊天记录等处跳转到底栏并拉取状态 */
export const FOTA_OPEN_PARSE_TASK = "fota_open_parse_task";

type ParseStatusPayload = {
  task_id?: string;
  status?: string;
  progress?: { percent?: number; stage?: string; message?: string };
  error?: string;
  result?: {
    total_files?: number;
    parsed_files?: number;
    total_events?: number;
    failed_files?: number;
    alignment_status?: string;
    [key: string]: unknown;
  };
  enqueue_time?: string | null;
  start_time?: string | null;
  finish_time?: string | null;
};

function formatStatus(p: ParseStatusPayload): string {
  const lines: string[] = [];
  const st = p.status || "unknown";
  lines.push(`状态: ${st}`);
  if (p.progress) {
    const { percent, stage, message } = p.progress;
    lines.push(
      `进度: ${percent ?? 0}%  [${stage ?? "-"}] ${message ?? ""}`.trim()
    );
  }
  if (p.enqueue_time) lines.push(`入队时间: ${p.enqueue_time}`);
  if (p.start_time) lines.push(`开始时间: ${p.start_time}`);
  if (p.finish_time) lines.push(`结束时间: ${p.finish_time}`);
  if (p.error) lines.push(`错误: ${p.error}`);
  if (p.result && st === "completed") {
    const r = p.result;
    lines.push(
      `结果: 解压 ${r.total_files ?? 0} 个文件, 成功解析 ${r.parsed_files ?? 0}, 事件数 ${r.total_events ?? 0}, 对齐 ${r.alignment_status ?? "-"}`
    );
  }
  return lines.join("\n");
}

const TASK_EVENT = "fota_last_parse_task_id";

export function rememberLastParseTaskId(taskId: string) {
  if (typeof window === "undefined" || !taskId) return;
  try {
    sessionStorage.setItem(LS_KEY, taskId);
    window.dispatchEvent(new CustomEvent(TASK_EVENT, { detail: taskId }));
  } catch {
    /* ignore */
  }
}

/**
 * 底部栏：用 task_id 轮询/查询 Arq 解析任务状态（走 Next /api/parse-status）。
 */
export default function TaskStatusLookup() {
  const [taskId, setTaskId] = useState("");
  const [resultText, setResultText] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [lastSaved, setLastSaved] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);

  const fetchStatus = useCallback(async (id: string) => {
    const tid = id.trim();
    if (!tid) {
      setResultText("请填写任务 ID。");
      return;
    }
    setLoading(true);
    setResultText(null);
    try {
      const res = await fetch(`/api/parse-status/${encodeURIComponent(tid)}`);
      const text = await res.text();
      let data: ParseStatusPayload;
      try {
        data = JSON.parse(text) as ParseStatusPayload;
      } catch {
        setResultText(`查询失败 (HTTP ${res.status}): ${text.slice(0, 200)}`);
        return;
      }
      if (!res.ok) {
        setResultText(`查询失败: ${(data as { detail?: string }).detail || text || res.status}`);
        return;
      }
      setResultText(formatStatus(data));
    } catch (e) {
      setResultText(`网络错误: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    try {
      const s = sessionStorage.getItem(LS_KEY);
      if (s) setLastSaved(s);
    } catch {
      /* ignore */
    }
    const onNew = (e: Event) => {
      const id = (e as CustomEvent<string>).detail;
      if (id) setLastSaved(id);
    };
    window.addEventListener(TASK_EVENT, onNew);
    const onOpen = (e: Event) => {
      const id = (e as CustomEvent<string>).detail?.trim();
      if (!id) return;
      setTaskId(id);
      void fetchStatus(id);
      requestAnimationFrame(() => {
        panelRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    };
    window.addEventListener(FOTA_OPEN_PARSE_TASK, onOpen);
    return () => {
      window.removeEventListener(TASK_EVENT, onNew);
      window.removeEventListener(FOTA_OPEN_PARSE_TASK, onOpen);
    };
  }, [fetchStatus]);

  return (
    <div
      ref={panelRef}
      style={{
        maxWidth: "48rem",
        margin: "10px auto 0",
        padding: "10px 12px",
        borderRadius: 12,
        border: "1px solid var(--border-color)",
        background: "var(--bg-input)",
        fontSize: 12,
        color: "var(--text-secondary)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 6 }}>
        <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>解析任务状态</span>
        <input
          type="text"
          value={taskId}
          onChange={(e) => setTaskId(e.target.value)}
          placeholder="task_id"
          style={{
            flex: "1 1 200px",
            minWidth: 0,
            padding: "6px 8px",
            borderRadius: 8,
            border: "1px solid var(--border-color)",
            background: "var(--bg-primary)",
            color: "var(--text-primary)",
            fontSize: 12,
            fontFamily: "ui-monospace, monospace",
          }}
        />
        <button
          type="button"
          disabled={loading}
          onClick={() => void fetchStatus(taskId)}
          style={{
            padding: "6px 12px",
            borderRadius: 8,
            border: "none",
            background: "var(--accent-blue)",
            color: "#fff",
            cursor: loading ? "not-allowed" : "pointer",
            fontSize: 12,
            fontWeight: 500,
            opacity: loading ? 0.7 : 1,
          }}
        >
          {loading ? "查询中…" : "查询"}
        </button>
        {lastSaved ? (
          <button
            type="button"
            onClick={() => {
              setTaskId(lastSaved);
              void fetchStatus(lastSaved);
            }}
            style={{
              padding: "6px 10px",
              borderRadius: 8,
              border: "1px solid var(--border-color)",
              background: "transparent",
              color: "var(--text-primary)",
              cursor: "pointer",
              fontSize: 11,
            }}
          >
            用最近上传
          </button>
        ) : null}
      </div>
      <p style={{ margin: 0, fontSize: 11, opacity: 0.85, lineHeight: 1.45 }}>
        大文件可能超过 4 分钟，界面会提前结束等待；可点上一条「日志上传结果」里的「查看状态」跳转到此并查询，或在此输入 task_id 后点「查询」。
      </p>
      {resultText ? (
        <pre
          style={{
            margin: "8px 0 0",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            fontSize: 11,
            lineHeight: 1.5,
            color: "var(--text-primary)",
            fontFamily: "ui-monospace, system-ui, sans-serif",
            background: "var(--bg-primary)",
            padding: 8,
            borderRadius: 8,
            border: "1px solid var(--border-color)",
          }}
        >
          {resultText}
        </pre>
      ) : null}
    </div>
  );
}
