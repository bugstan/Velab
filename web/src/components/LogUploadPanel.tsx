"use client";

import { useEffect, useMemo, useState } from "react";
import { LOG_SOURCE_TYPES, LogSourceType } from "@/lib/types";

type UploadedItem = {
  file_id: string;
  original_filename: string;
  source_type: string;
  parse_status: string;
  uploaded_at: string;
};

type ListResponse = {
  total: number;
  items: UploadedItem[];
};

interface LogUploadPanelProps {
  caseId: string;
  onCaseIdChange: (caseId: string) => void;
  onUploadSuccess?: () => void;
}

function generateCaseId() {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  const hh = String(now.getHours()).padStart(2, "0");
  const mi = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  const rand = Math.random().toString(36).slice(2, 6).toUpperCase();
  return `CASE_${yyyy}${mm}${dd}_${hh}${mi}${ss}_${rand}`;
}

export default function LogUploadPanel({ caseId, onCaseIdChange, onUploadSuccess }: LogUploadPanelProps) {
  const [sourceType, setSourceType] = useState<LogSourceType>("android");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [items, setItems] = useState<UploadedItem[]>([]);
  const [open, setOpen] = useState(false);

  const canUpload = useMemo(() => caseId.trim().length > 0 && !!file && !loading, [caseId, file, loading]);

  useEffect(() => {
    if (!caseId.trim()) {
      onCaseIdChange(generateCaseId());
    }
  }, [caseId, onCaseIdChange]);

  const loadList = async (targetCaseId: string) => {
    if (!targetCaseId.trim()) return;
    const res = await fetch(`/api/logfiles?case_id=${encodeURIComponent(targetCaseId)}&limit=20`, {
      method: "GET",
    });
    if (!res.ok) return;
    const data = (await res.json()) as ListResponse;
    setItems(data.items || []);
  };

  useEffect(() => {
    if (!open) return;
    loadList(caseId).catch(() => undefined);
  }, [open, caseId]);

  const onUpload = async () => {
    if (!canUpload || !file) return;
    setLoading(true);
    setMessage("");
    try {
      // 上传前确保 Case 存在；已存在时后端会返回 409，可直接忽略
      const caseCreateRes = await fetch("/api/cases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_id: caseId.trim() }),
      });
      if (!caseCreateRes.ok && caseCreateRes.status !== 409) {
        const caseErr = await caseCreateRes.json().catch(() => ({}));
        setMessage(caseErr?.detail || caseErr?.error || "创建 Case 失败");
        return;
      }

      const form = new FormData();
      form.append("case_id", caseId.trim());
      form.append("source_type", sourceType);
      form.append("file", file);

      const res = await fetch("/api/logfiles/upload", {
        method: "POST",
        body: form,
      });
      const data = await res.json();
      if (!res.ok) {
        setMessage(data?.detail || data?.error || "上传失败");
      } else {
        setMessage(`上传成功: ${data.original_filename}`);
        setFile(null);
        await loadList(caseId);
        onUploadSuccess?.();
      }
    } catch {
      setMessage("上传失败，请检查网络连接");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section
      className="border-b"
      style={{ borderColor: "var(--border-color)", background: "var(--bg-secondary)" }}
    >
      <div className="max-w-4xl mx-auto px-4 py-2">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="text-sm font-medium hover:opacity-80 transition-opacity cursor-pointer"
          style={{ color: "var(--text-primary)" }}
        >
          {open ? "隐藏日志上传面板" : "展开日志上传面板"}
        </button>

        {open && (
          <div className="mt-3 grid grid-cols-1 md:grid-cols-5 gap-2 items-end">
            <div className="md:col-span-2">
              <label className="text-xs block mb-1" style={{ color: "var(--text-secondary)" }}>
                Case ID
              </label>
              <div className="flex gap-2">
                <input
                  value={caseId}
                  readOnly
                  className="w-full rounded-md border px-3 py-2 text-sm"
                  style={{
                    borderColor: "var(--border-color)",
                    background: "var(--bg-primary)",
                    color: "var(--text-primary)",
                  }}
                />
                <button
                  type="button"
                  onClick={() => onCaseIdChange(generateCaseId())}
                  className="rounded-md px-3 py-2 text-xs border"
                  style={{ borderColor: "var(--border-color)", color: "var(--text-secondary)" }}
                >
                  新建
                </button>
              </div>
            </div>

            <div>
              <label className="text-xs block mb-1" style={{ color: "var(--text-secondary)" }}>
                日志类型
              </label>
              <select
                value={sourceType}
                onChange={(e) => setSourceType(e.target.value as LogSourceType)}
                className="w-full rounded-md border px-3 py-2 text-sm"
                style={{
                  borderColor: "var(--border-color)",
                  background: "var(--bg-primary)",
                  color: "var(--text-primary)",
                }}
              >
                {LOG_SOURCE_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-xs block mb-1" style={{ color: "var(--text-secondary)" }}>
                文件
              </label>
              <input
                type="file"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                accept=".log,.txt,.dlt,.zip,.tar,.gz,.tgz,.rar"
                className="w-full text-sm"
                style={{ color: "var(--text-primary)" }}
              />
              <div className="text-[11px] mt-1" style={{ color: "var(--text-secondary)" }}>
                支持单日志文件或压缩包（zip/tar.gz/rar）
              </div>
            </div>

            <button
              type="button"
              onClick={onUpload}
              disabled={!canUpload}
              className="rounded-md px-3 py-2 text-sm font-medium transition-opacity disabled:opacity-40"
              style={{ background: "var(--accent-blue)", color: "white" }}
            >
              {loading ? "上传中..." : "上传日志"}
            </button>

            {message && (
              <div className="md:col-span-5 text-sm" style={{ color: "var(--text-secondary)" }}>
                {message}
              </div>
            )}

            <div className="md:col-span-5 mt-1">
              <div className="text-xs mb-1" style={{ color: "var(--text-secondary)" }}>
                最近上传（当前 Case）
              </div>
              <div className="max-h-28 overflow-auto rounded-md border" style={{ borderColor: "var(--border-color)" }}>
                {items.length === 0 ? (
                  <div className="px-3 py-2 text-sm" style={{ color: "var(--text-secondary)" }}>
                    暂无上传记录
                  </div>
                ) : (
                  items.map((it) => (
                    <div
                      key={it.file_id}
                      className="px-3 py-2 text-xs border-b last:border-b-0"
                      style={{ borderColor: "var(--border-color)", color: "var(--text-primary)" }}
                    >
                      <span className="font-medium">{it.original_filename}</span>
                      <span className="ml-2 opacity-80">[{it.source_type}]</span>
                      <span className="ml-2 opacity-70">{it.parse_status}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
