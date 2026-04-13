"use client";

import { useEffect, useMemo, useState } from "react";

type UploadedItem = {
  file_id: string;
  case_id: string;
  original_filename: string;
  source_type: string;
  parse_status: string;
  uploaded_at: string;
};

type ListResponse = {
  total: number;
  items: UploadedItem[];
};

interface UploadedCaseSidebarProps {
  selectedCaseId: string;
  onSelectCase: (caseId: string) => void;
  refreshSignal?: number;
  onRecordsChanged?: () => void;
}

type CaseAggregate = {
  caseId: string;
  latestUploadedAt: string;
  counts: { PENDING: number; PARSED: number; FAILED: number; OTHER: number };
};

function fmtTime(ts: string) {
  if (!ts) return "-";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleString("zh-CN", { hour12: false });
}

export default function UploadedCaseSidebar({
  selectedCaseId,
  onSelectCase,
  refreshSignal = 0,
  onRecordsChanged,
}: UploadedCaseSidebarProps) {
  const [items, setItems] = useState<UploadedItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [parseLoading, setParseLoading] = useState(false);
  const [alignLoading, setAlignLoading] = useState(false);
  const [taskId, setTaskId] = useState("");
  const [taskStatus, setTaskStatus] = useState("");
  const [taskMessage, setTaskMessage] = useState("");

  const loadUploadRecords = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/logfiles?limit=500", { method: "GET" });
      if (!res.ok) return;
      const data = (await res.json()) as ListResponse;
      setItems(data.items || []);
    } finally {
      setLoading(false);
    }
  };

  const submitParseTask = async () => {
    if (!selectedCaseId) return;
    setParseLoading(true);
    setTaskMessage("");
    try {
      const res = await fetch("/api/parse/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_id: selectedCaseId }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setTaskMessage(data?.detail || data?.error || "提交解析任务失败");
        return;
      }
      const tid = data?.task_id || "";
      setTaskId(tid);
      setTaskStatus(data?.status || "pending");
      setTaskMessage(`解析任务已提交: ${tid}`);
    } catch {
      setTaskMessage("提交解析任务失败，请检查网络");
    } finally {
      setParseLoading(false);
    }
  };

  const alignCaseTime = async () => {
    if (!selectedCaseId) return;
    setAlignLoading(true);
    setTaskMessage("");
    try {
      const res = await fetch(`/api/parse/align-time/${encodeURIComponent(selectedCaseId)}`, {
        method: "POST",
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setTaskMessage(data?.detail || data?.error || "时间对齐失败");
        return;
      }
      setTaskMessage(data?.message || "时间对齐完成");
      await loadUploadRecords();
      onRecordsChanged?.();
    } catch {
      setTaskMessage("时间对齐失败，请检查网络");
    } finally {
      setAlignLoading(false);
    }
  };

  useEffect(() => {
    if (!taskId) return;
    const timer = setInterval(async () => {
      try {
        const res = await fetch(`/api/parse/status/${encodeURIComponent(taskId)}`, { method: "GET" });
        if (!res.ok) return;
        const data = await res.json();
        const status = data?.status || "unknown";
        setTaskStatus(status);
        if (status === "completed") {
          setTaskMessage("解析任务完成");
          await loadUploadRecords();
          onRecordsChanged?.();
          clearInterval(timer);
        } else if (status === "failed" || status === "not_found") {
          setTaskMessage(data?.error || `任务状态: ${status}`);
          clearInterval(timer);
        }
      } catch {
        // noop
      }
    }, 2000);

    return () => clearInterval(timer);
  }, [taskId, onRecordsChanged]);

  useEffect(() => {
    loadUploadRecords().catch(() => undefined);
  }, [refreshSignal]);

  const uploadRecords = useMemo<UploadedItem[]>(() => {
    return [...items].sort(
      (a, b) => new Date(b.uploaded_at).getTime() - new Date(a.uploaded_at).getTime()
    );
  }, [items]);

  const caseList = useMemo<CaseAggregate[]>(() => {
    const map = new Map<string, CaseAggregate>();
    for (const r of uploadRecords) {
      const key = r.case_id;
      const st = (r.parse_status || "").toUpperCase();
      const curr = map.get(key);
      if (!curr) {
        map.set(key, {
          caseId: key,
          latestUploadedAt: r.uploaded_at,
          counts: {
            PENDING: st === "PENDING" ? 1 : 0,
            PARSED: st === "PARSED" ? 1 : 0,
            FAILED: st === "FAILED" ? 1 : 0,
            OTHER: ["PENDING", "PARSED", "FAILED"].includes(st) ? 0 : 1,
          },
        });
      } else {
        if (new Date(r.uploaded_at).getTime() > new Date(curr.latestUploadedAt).getTime()) {
          curr.latestUploadedAt = r.uploaded_at;
        }
        if (st === "PENDING") curr.counts.PENDING += 1;
        else if (st === "PARSED") curr.counts.PARSED += 1;
        else if (st === "FAILED") curr.counts.FAILED += 1;
        else curr.counts.OTHER += 1;
      }
    }
    return Array.from(map.values()).sort(
      (a, b) => new Date(b.latestUploadedAt).getTime() - new Date(a.latestUploadedAt).getTime()
    );
  }, [uploadRecords]);

  useEffect(() => {
    if (!selectedCaseId && caseList.length > 0) {
      onSelectCase(caseList[0].caseId);
    }
  }, [selectedCaseId, caseList, onSelectCase]);

  const selectedRecords = useMemo(() => {
    return uploadRecords.filter((r) => r.case_id === selectedCaseId);
  }, [uploadRecords, selectedCaseId]);

  const selectedGroupedByType = useMemo(() => {
    const groups = new Map<string, UploadedItem[]>();
    for (const r of selectedRecords) {
      if (!groups.has(r.source_type)) groups.set(r.source_type, []);
      groups.get(r.source_type)!.push(r);
    }
    return Array.from(groups.entries());
  }, [selectedRecords]);

  return (
    <aside
      className="w-full md:w-72 md:min-w-72 border-r"
      style={{ borderColor: "var(--border-color)", background: "var(--bg-secondary)" }}
    >
      <div className="px-3 py-3 border-b flex items-center justify-between" style={{ borderColor: "var(--border-color)" }}>
        <div>
          <div className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
            Case 列表
          </div>
          <div className="text-xs" style={{ color: "var(--text-secondary)" }}>
            {caseList.length} 个 Case
          </div>
        </div>
        <button
          type="button"
          onClick={() => loadUploadRecords().catch(() => undefined)}
          className="text-xs px-2 py-1 rounded border"
          style={{ borderColor: "var(--border-color)", color: "var(--text-secondary)" }}
        >
          刷新
        </button>
      </div>

      <div className="max-h-[calc(100vh-220px)] overflow-auto">
        {loading ? (
          <div className="px-3 py-3 text-sm" style={{ color: "var(--text-secondary)" }}>
            加载中...
          </div>
        ) : caseList.length === 0 ? (
          <div className="px-3 py-3 text-sm" style={{ color: "var(--text-secondary)" }}>
            暂无上传记录
          </div>
        ) : (
          caseList.map((c) => {
            const active = c.caseId === selectedCaseId;
            return (
              <button
                key={c.caseId}
                type="button"
                onClick={() => onSelectCase(c.caseId)}
                className="w-full text-left px-3 py-2 border-b transition-opacity hover:opacity-85"
                style={{
                  borderColor: "var(--border-color)",
                  background: active ? "var(--bg-tertiary)" : "transparent",
                  color: "var(--text-primary)",
                }}
              >
                <div className="text-sm font-medium truncate">{c.caseId}</div>
                <div className="text-[11px] truncate" style={{ color: "var(--text-secondary)" }}>
                  最近上传: {fmtTime(c.latestUploadedAt)}
                </div>
                <div className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
                  P:{c.counts.PENDING} / D:{c.counts.PARSED} / F:{c.counts.FAILED}
                </div>
              </button>
            );
          })
        )}

        {selectedCaseId && (
          <div className="px-3 py-3 border-t" style={{ borderColor: "var(--border-color)" }}>
            <div className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              Case 详情
            </div>
            <div className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
              {selectedCaseId}
            </div>
            <div className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
              文件数: {selectedRecords.length}
            </div>

            <div className="mt-2 space-y-2">
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => submitParseTask().catch(() => undefined)}
                  disabled={parseLoading || selectedRecords.length === 0}
                  className="rounded px-2 py-1 text-xs font-medium disabled:opacity-40"
                  style={{ background: "var(--accent-blue)", color: "#fff" }}
                >
                  {parseLoading ? "提交中..." : "提交解析"}
                </button>
                <button
                  type="button"
                  onClick={() => alignCaseTime().catch(() => undefined)}
                  disabled={alignLoading || selectedRecords.length === 0}
                  className="rounded px-2 py-1 text-xs font-medium disabled:opacity-40"
                  style={{ background: "var(--accent-red)", color: "#fff" }}
                >
                  {alignLoading ? "对齐中..." : "时间对齐"}
                </button>
              </div>

              {(taskId || taskStatus || taskMessage) && (
                <div className="text-xs rounded border px-2 py-1" style={{ borderColor: "var(--border-color)", color: "var(--text-secondary)" }}>
                  {taskId ? `任务: ${taskId}` : ""}
                  {taskStatus ? ` · 状态: ${taskStatus}` : ""}
                  {taskMessage ? ` · ${taskMessage}` : ""}
                </div>
              )}

              {selectedGroupedByType.length === 0 ? (
                <div className="text-xs" style={{ color: "var(--text-secondary)" }}>暂无该 Case 上传文件</div>
              ) : (
                selectedGroupedByType.map(([type, recs]) => (
                  <div key={type} className="rounded border" style={{ borderColor: "var(--border-color)" }}>
                    <div className="px-2 py-1 text-xs font-medium" style={{ color: "var(--text-primary)", background: "var(--bg-tertiary)" }}>
                      {type} ({recs.length})
                    </div>
                    <div className="max-h-36 overflow-auto">
                      {recs.map((r) => (
                        <div key={r.file_id} className="px-2 py-1 border-t" style={{ borderColor: "var(--border-color)" }}>
                          <div className="text-xs truncate" style={{ color: "var(--text-primary)" }}>{r.original_filename}</div>
                          <div className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
                            {fmtTime(r.uploaded_at)} · {r.parse_status}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
