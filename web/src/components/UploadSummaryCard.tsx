"use client";

import { UploadSummary } from "@/lib/types";

interface UploadSummaryCardProps {
  summary: UploadSummary;
}

type Lane = {
  controller: string;
  count: number;
  start?: number;
  end?: number;
};

const toIso = (value?: number): string => {
  if (typeof value !== "number" || Number.isNaN(value)) return "无有效时间";
  return new Date(value * 1000).toISOString();
};

export default function UploadSummaryCard({ summary }: UploadSummaryCardProps) {
  const lanes: Lane[] = Object.entries(summary.filesByController).map(([controller, count]) => ({
    controller,
    count,
    start: summary.validTimeRangeByController[controller]?.start,
    end: summary.validTimeRangeByController[controller]?.end,
  }));

  const validRanges = lanes.filter((lane) => typeof lane.start === "number" && typeof lane.end === "number");
  const globalStart = validRanges.length > 0 ? Math.min(...validRanges.map((lane) => lane.start as number)) : undefined;
  const globalEnd = validRanges.length > 0 ? Math.max(...validRanges.map((lane) => lane.end as number)) : undefined;
  const totalSpan = typeof globalStart === "number" && typeof globalEnd === "number" && globalEnd > globalStart
    ? globalEnd - globalStart
    : 0;

  return (
    <section
      className="mt-3 rounded-xl border p-3"
      style={{ borderColor: "var(--border-color)", background: "var(--bg-secondary)" }}
    >
      <div className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
        上传 Summary · {summary.fileName}
      </div>
      <div className="mt-1 text-xs" style={{ color: "var(--text-secondary)" }}>
        共 {summary.fileCount} 个文件，{Object.keys(summary.filesByController).length} 类日志
      </div>

      <div className="mt-3 text-xs" style={{ color: "var(--text-secondary)" }}>
        全局时间窗口：{toIso(globalStart)} ~ {toIso(globalEnd)}
      </div>

      <div className="mt-3 grid gap-2">
        {lanes.map((lane, idx) => {
          const hasRange = totalSpan > 0 && typeof lane.start === "number" && typeof lane.end === "number" && lane.end >= lane.start;
          const leftPct = hasRange ? (((lane.start as number) - (globalStart as number)) / totalSpan) * 100 : 0;
          const widthPct = hasRange ? (((lane.end as number) - (lane.start as number)) / totalSpan) * 100 : 0;
          return (
            <div key={lane.controller} className="grid gap-1">
              <div className="flex items-center justify-between text-xs">
                <span style={{ color: "var(--text-primary)" }}>
                  {lane.controller} ({lane.count})
                </span>
                <span style={{ color: "var(--text-secondary)" }}>
                  {toIso(lane.start)} ~ {toIso(lane.end)}
                </span>
              </div>
              <div className="relative h-4 rounded-full" style={{ background: "var(--border-light)" }}>
                {hasRange ? (
                  <div
                    className="absolute top-0 h-4 rounded-full"
                    style={{
                      left: `${Math.max(0, Math.min(100, leftPct))}%`,
                      width: `${Math.max(2, Math.min(100, widthPct || 2))}%`,
                      background: idx % 2 === 0 ? "var(--accent-blue)" : "#a371f7",
                    }}
                    title={`${lane.controller}: ${toIso(lane.start)} ~ ${toIso(lane.end)}`}
                  />
                ) : (
                  <div className="absolute inset-0 flex items-center justify-center text-[10px]" style={{ color: "var(--text-muted)" }}>
                    无有效时间
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
