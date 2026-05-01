"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const LS_KEY = "fota_last_bundle_id";

/** 从聊天记录等处跳转到底栏并拉取状态 */
export const FOTA_OPEN_BUNDLE_STATUS = "fota_open_bundle_status";

type BundleStatusPayload = {
  bundle_id?: string;
  status?: string;          // queued | extracting | decoding | prescanning | aligning | done | failed
  progress?: number;        // 0.0 — 1.0
  archive_filename?: string;
  archive_size_bytes?: number;
  error?: string | null;
  file_count?: number;
  files_by_controller?: Record<string, number>;
};

function formatStatus(p: BundleStatusPayload): string {
  const lines: string[] = [];
  const st = p.status || "unknown";
  lines.push(`状态: ${st}`);
  if (typeof p.progress === "number") {
    lines.push(`进度: ${(p.progress * 100).toFixed(1)}%`);
  }
  if (p.archive_filename) lines.push(`文件: ${p.archive_filename}`);
  if (typeof p.archive_size_bytes === "number") {
    lines.push(`大小: ${(p.archive_size_bytes / (1024 * 1024)).toFixed(2)} MB`);
  }
  if (typeof p.file_count === "number") {
    lines.push(`已分类文件: ${p.file_count}`);
  }
  if (p.files_by_controller && Object.keys(p.files_by_controller).length > 0) {
    const parts = Object.entries(p.files_by_controller)
      .map(([k, v]) => `${k}=${v}`)
      .join(", ");
    lines.push(`按控制器: ${parts}`);
  }
  if (p.error) lines.push(`错误: ${p.error}`);
  return lines.join("\n");
}

const BUNDLE_EVENT = "fota_last_bundle_id";

export function rememberLastBundleId(bundleId: string) {
  if (typeof window === "undefined" || !bundleId) return;
  try {
    sessionStorage.setItem(LS_KEY, bundleId);
    window.dispatchEvent(new CustomEvent(BUNDLE_EVENT, { detail: bundleId }));
  } catch {
    /* ignore */
  }
}

/**
 * 底部栏：用 bundle_id 查询 log_pipeline 摄取状态（走 Next /api/bundle-status）。
 */
export default function TaskStatusLookup() {
  const [bundleId, setBundleId] = useState("");
  const [resultText, setResultText] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [lastSaved, setLastSaved] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);

  const fetchStatus = useCallback(async (id: string) => {
    const bid = id.trim();
    if (!bid) {
      setResultText("请填写 bundle ID。");
      return;
    }
    setLoading(true);
    setResultText(null);
    try {
      const res = await fetch(`/api/bundle-status/${encodeURIComponent(bid)}`);
      const text = await res.text();
      let data: BundleStatusPayload;
      try {
        data = JSON.parse(text) as BundleStatusPayload;
      } catch {
        setResultText(`查询失败 (HTTP ${res.status}): ${text.slice(0, 200)}`);
        return;
      }
      if (!res.ok) {
        const errPayload = data as { detail?: string; error?: { message?: string } | string | null };
        const errStr = typeof errPayload.error === "object" && errPayload.error
          ? errPayload.error.message
          : (typeof errPayload.error === "string" ? errPayload.error : undefined);
        setResultText(`查询失败: ${errPayload.detail || errStr || text || res.status}`);
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
    window.addEventListener(BUNDLE_EVENT, onNew);
    const onOpen = (e: Event) => {
      const id = (e as CustomEvent<string>).detail?.trim();
      if (!id) return;
      setBundleId(id);
      void fetchStatus(id);
      requestAnimationFrame(() => {
        panelRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    };
    window.addEventListener(FOTA_OPEN_BUNDLE_STATUS, onOpen);
    return () => {
      window.removeEventListener(BUNDLE_EVENT, onNew);
      window.removeEventListener(FOTA_OPEN_BUNDLE_STATUS, onOpen);
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
        <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>Bundle 摄取状态</span>
        <input
          type="text"
          value={bundleId}
          onChange={(e) => setBundleId(e.target.value)}
          placeholder="bundle_id"
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
          onClick={() => void fetchStatus(bundleId)}
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
              setBundleId(lastSaved);
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
        大文件可能超过 4 分钟，界面会提前结束等待；可点上一条「日志上传结果」里的「查看状态」跳转到此并查询，或在此输入 bundle_id 后点「查询」。
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
