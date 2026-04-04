"use client";

import { useState } from "react";
import { SourceReference } from "@/lib/types";

interface SourcePanelProps {
  sources: SourceReference[];
}

export default function SourcePanel({ sources }: SourcePanelProps) {
  const [selectedSource, setSelectedSource] = useState<Source | null>(null);

  if (sources.length === 0) return null;

  const getSourceIcon = (type: SourceReference["type"]) => {
    switch (type) {
      case "log":
        return "📄";
      case "jira":
        return "🎫";
      case "document":
        return "📚";
      case "pdf":
        return "📑";
      default:
        return "📌";
    }
  };

  const getSourceTypeLabel = (type: SourceReference["type"]) => {
    switch (type) {
      case "log":
        return "日志";
      case "jira":
        return "Jira工单";
      case "document":
        return "技术文档";
      case "pdf":
        return "PDF文档";
      default:
        return "来源";
    }
  };

  return (
    <div className="mt-4">
      <div
        className="text-xs font-medium mb-2"
        style={{ color: "var(--text-secondary)" }}
      >
        证据来源 ({sources.length})
      </div>
      
      <div className="flex flex-wrap gap-2">
        {sources.map((source, index) => (
          <button
            key={`${source.type}-${index}`}
            onClick={() => source.url ? window.open(source.url, '_blank') : setSelectedSource(source)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-all hover:opacity-80"
            style={{
              background: "var(--bg-tertiary)",
              border: "1px solid var(--border-color)",
              color: "var(--text-secondary)",
            }}
          >
            <span>{getSourceIcon(source.type)}</span>
            <span>{source.title}</span>
            {source.url && (
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M9 3L3 9M9 3H5M9 3V7" />
              </svg>
            )}
          </button>
        ))}
      </div>

      {selectedSource && !selectedSource.url && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: "rgba(0, 0, 0, 0.7)" }}
          onClick={() => setSelectedSource(null)}
        >
          <div
            className="max-w-3xl w-full max-h-[80vh] rounded-xl overflow-hidden"
            style={{
              background: "var(--bg-primary)",
              border: "1px solid var(--border-color)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              className="flex items-center justify-between px-5 py-4 border-b"
              style={{ borderColor: "var(--border-color)" }}
            >
              <div className="flex items-center gap-2">
                <span className="text-lg">{getSourceIcon(selectedSource.type)}</span>
                <div>
                  <div
                    className="text-sm font-semibold"
                    style={{ color: "var(--text-primary)" }}
                  >
                    {selectedSource.title}
                  </div>
                  <div
                    className="text-xs mt-0.5"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {getSourceTypeLabel(selectedSource.type)}
                  </div>
                </div>
              </div>
              
              <button
                onClick={() => setSelectedSource(null)}
                className="w-8 h-8 rounded-lg flex items-center justify-center transition-opacity hover:opacity-60"
                style={{ background: "var(--bg-tertiary)" }}
              >
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  style={{ color: "var(--text-secondary)" }}
                >
                  <path d="M4 4L12 12M12 4L4 12" />
                </svg>
              </button>
            </div>

            <div
              className="p-5 overflow-y-auto"
              style={{ maxHeight: "calc(80vh - 80px)" }}
            >
              <div
                className="text-sm leading-relaxed"
                style={{ color: "var(--text-secondary)" }}
              >
                <p>此来源暂无详细内容预览。</p>
                <p className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
                  提示：带有链接的来源可以点击打开查看完整内容。
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
