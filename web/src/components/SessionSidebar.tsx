"use client";

import { useState } from "react";
import { ChatSession } from "@/lib/types";

interface SessionSidebarProps {
  sessions: ChatSession[];
  activeSessionId?: string;
  onSelectSession: (sessionId: string) => void;
  onCreateSession: () => void;
  onDeleteSession: (sessionId: string) => void;
}

const getRelativeTimeLabel = (value: Date): string => {
  const deltaSec = Math.max(0, Math.floor((Date.now() - value.getTime()) / 1000));
  if (deltaSec < 60) return "刚刚";
  if (deltaSec < 3600) return `${Math.floor(deltaSec / 60)} 分钟前`;
  if (deltaSec < 86400) return `${Math.floor(deltaSec / 3600)} 小时前`;
  return `${Math.floor(deltaSec / 86400)} 天前`;
};

export default function SessionSidebar({
  sessions,
  activeSessionId,
  onSelectSession,
  onCreateSession,
  onDeleteSession,
}: SessionSidebarProps) {
  const [openMenuSessionId, setOpenMenuSessionId] = useState<string | null>(null);

  return (
    <aside
      className="h-full border-r"
      style={{
        width: 280,
        borderColor: "var(--border-color)",
        background: "var(--bg-secondary)",
      }}
    >
      <div className="p-3 border-b" style={{ borderColor: "var(--border-color)" }}>
        <button
          type="button"
          onClick={onCreateSession}
          className="w-full rounded-lg px-3 py-2 text-sm font-medium"
          style={{
            background: "var(--accent-blue)",
            color: "#fff",
            border: "none",
            cursor: "pointer",
          }}
        >
          新建聊天
        </button>
      </div>

      <div className="p-2 overflow-y-auto" style={{ height: "calc(100% - 61px)" }}>
        {sessions.length === 0 ? (
          <div className="px-2 py-3 text-xs" style={{ color: "var(--text-muted)" }}>
            暂无会话，发送第一条消息后会出现在这里。
          </div>
        ) : sessions.map((session) => {
          const active = session.id === activeSessionId;
          const msgCount = session.messages.length;
          return (
            <div
              key={session.id}
              className="relative mb-2 group"
            >
              <button
                type="button"
                onClick={() => onSelectSession(session.id)}
                className="w-full rounded-lg p-3 pr-12 text-left transition-opacity hover:opacity-90"
                style={{
                  background: active ? "var(--bg-tertiary)" : "transparent",
                  border: `1px solid ${active ? "var(--accent-blue)" : "var(--border-color)"}`,
                  cursor: "pointer",
                }}
              >
                <div className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>
                  {session.title || "新会话"}
                </div>
                <div className="mt-1 text-xs" style={{ color: "var(--text-secondary)" }}>
                  {getRelativeTimeLabel(session.updatedAt)} · {msgCount} 条消息
                </div>
              </button>

              <div className="absolute top-2 right-2">
                <button
                  type="button"
                  aria-label="会话操作"
                  onClick={(e) => {
                    e.stopPropagation();
                    setOpenMenuSessionId((prev) => (prev === session.id ? null : session.id));
                  }}
                  className="h-7 w-7 rounded-md text-sm transition-opacity opacity-0 group-hover:opacity-100 focus:opacity-100"
                  style={{
                    background: "var(--bg-input)",
                    border: "1px solid var(--border-color)",
                    color: "var(--text-secondary)",
                    cursor: "pointer",
                  }}
                >
                  ⋯
                </button>

                {openMenuSessionId === session.id ? (
                  <div
                    className="absolute right-0 mt-1 min-w-[96px] rounded-md border py-1 shadow-lg z-10"
                    style={{
                      background: "var(--bg-primary)",
                      borderColor: "var(--border-color)",
                    }}
                  >
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setOpenMenuSessionId(null);
                        const ok = window.confirm(`确认删除会话「${session.title || "新会话"}」吗？`);
                        if (!ok) return;
                        onDeleteSession(session.id);
                      }}
                      className="w-full px-3 py-1.5 text-left text-xs hover:opacity-80"
                      style={{
                        color: "#f85149",
                        background: "transparent",
                        border: "none",
                        cursor: "pointer",
                      }}
                    >
                      删除
                    </button>
                  </div>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
    </aside>
  );
}
