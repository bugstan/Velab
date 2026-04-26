"use client";

import { useRef, useState } from "react";
import TaskStatusLookup from "@/components/TaskStatusLookup";

interface InputBarProps {
  onSend: (message: string) => void;
  isRunning: boolean;
  onStop: () => void;
  onUploadFiles: (files: FileList | File[]) => Promise<void>;
  uploadProgress?: {
    active: boolean;
    percent: number;
    stage: string;
    message: string;
  };
}

export default function InputBar({ onSend, isRunning, onStop, onUploadFiles, uploadProgress }: InputBarProps) {
  const [input, setInput] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (input.trim() && !isRunning) {
      onSend(input.trim());
      setInput("");
    }
  }

  async function handleFiles(files: FileList | File[]) {
    if (!files || files.length === 0) return;
    await onUploadFiles(files);
  }

  return (
    <div
      style={{
        position: "sticky",
        bottom: 0,
        width: "100%",
        padding: "8px 16px 16px",
        background: "var(--bg-primary)",
        zIndex: 100,
      }}
    >
      <form
        onSubmit={handleSubmit}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          setIsDragging(false);
        }}
        onDrop={async (e) => {
          e.preventDefault();
          setIsDragging(false);
          await handleFiles(e.dataTransfer.files);
        }}
        style={{
          maxWidth: "48rem",
          margin: "0 auto",
          display: "flex",
          alignItems: "center",
          gap: "8px",
          borderRadius: "16px",
          border: "1px solid var(--border-color)",
          background: "var(--bg-input)",
          padding: "8px 12px",
          border: isDragging ? "1px solid var(--accent-blue)" : "1px solid var(--border-color)",
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          style={{ display: "none" }}
          onChange={async (e) => {
            if (e.target.files) await handleFiles(e.target.files);
            e.currentTarget.value = "";
          }}
        />
        {/* + button */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          style={{
            flexShrink: 0,
            width: 32,
            height: 32,
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "var(--border-color)",
            color: "var(--text-secondary)",
            border: "none",
            cursor: "pointer",
          }}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M8 3V13M3 8H13" />
          </svg>
        </button>

        {/* text input */}
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question"
          style={{
            flex: 1,
            background: "transparent",
            border: "none",
            outline: "none",
            color: "var(--text-primary)",
            fontSize: 14,
            padding: "6px 0",
          }}
        />

        {/* attachment icon */}
        <button
          type="button"
            onClick={() => fileInputRef.current?.click()}
          style={{
            flexShrink: 0,
            width: 32,
            height: 32,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "transparent",
            color: "var(--text-muted)",
            border: "none",
            cursor: "pointer",
          }}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M14 10V12.5C14 13.3284 13.3284 14 12.5 14H3.5C2.67157 14 2 13.3284 2 12.5V10" />
            <path d="M4.5 6.5L8 2.5L11.5 6.5" />
            <path d="M8 2.5V10" />
          </svg>
        </button>

        {/* microphone icon */}
        <button
          type="button"
          style={{
            flexShrink: 0,
            width: 32,
            height: 32,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "transparent",
            color: "var(--text-muted)",
            border: "none",
            cursor: "pointer",
          }}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M8 1.5V10.5" />
            <path d="M11 4C11 2.61929 9.65685 1.5 8 1.5C6.34315 1.5 5 2.61929 5 4V8C5 9.65685 6.34315 11 8 11C9.65685 11 11 9.65685 11 8V4Z" />
            <path d="M3 8C3 10.7614 5.23858 13 8 13C10.7614 13 13 10.7614 13 8" />
            <path d="M8 13V14.5" />
          </svg>
        </button>

        {/* Run / Stop button */}
        {isRunning ? (
          <button
            type="button"
            onClick={onStop}
            style={{
              flexShrink: 0,
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "6px 14px",
              borderRadius: 8,
              background: "var(--border-color)",
              color: "var(--text-primary)",
              border: "none",
              cursor: "pointer",
              fontSize: 14,
              fontWeight: 500,
            }}
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
              <rect x="2" y="2" width="8" height="8" rx="1" />
            </svg>
            Stop
          </button>
        ) : (
          <button
            type="submit"
            style={{
              flexShrink: 0,
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "6px 14px",
              borderRadius: 8,
              background: "var(--accent-blue)",
              color: "#fff",
              border: "none",
              cursor: "pointer",
              fontSize: 14,
              fontWeight: 500,
              opacity: input.trim() ? 1 : 0.5,
            }}
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M6 10V2M2 6L6 2L10 6" />
            </svg>
            Run
          </button>
        )}
      </form>
      {uploadProgress?.active ? (
        <div style={{ maxWidth: "48rem", margin: "8px auto 0", color: "var(--text-secondary)", fontSize: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
            <span>{uploadProgress.message || "处理中..."}</span>
            <span>{Math.max(0, Math.min(100, uploadProgress.percent))}%</span>
          </div>
          <div style={{ width: "100%", height: 6, background: "var(--border-color)", borderRadius: 999 }}>
            <div
              style={{
                width: `${Math.max(0, Math.min(100, uploadProgress.percent))}%`,
                height: "100%",
                background: "var(--accent-blue)",
                borderRadius: 999,
                transition: "width 240ms ease",
              }}
            />
          </div>
        </div>
      ) : null}
      <TaskStatusLookup />
    </div>
  );
}
