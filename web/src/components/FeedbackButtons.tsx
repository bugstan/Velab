"use client";

import { useState } from "react";

export default function FeedbackButtons() {
  const [liked, setLiked] = useState<boolean | null>(null);
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex items-center gap-1 mt-3 pt-2" style={{ borderTop: "1px solid var(--border-light)" }}>
      <button
        onClick={handleCopy}
        className="p-1.5 rounded-md transition-opacity hover:opacity-80 cursor-pointer"
        style={{ color: copied ? "var(--accent-blue)" : "var(--text-muted)" }}
        title="Copy"
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
          {copied ? (
            <path d="M3 7L6 10L11 4" />
          ) : (
            <>
              <rect x="4" y="4" width="8" height="8" rx="1" />
              <path d="M10 4V3C10 2.44772 9.55228 2 9 2H3C2.44772 2 2 2.44772 2 3V9C2 9.55228 2.44772 10 3 10H4" />
            </>
          )}
        </svg>
      </button>

      <button
        className="p-1.5 rounded-md transition-opacity hover:opacity-80 cursor-pointer"
        style={{ color: "var(--text-muted)" }}
        title="Regenerate"
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M1.5 7C1.5 3.96243 3.96243 1.5 7 1.5C10.0376 1.5 12.5 3.96243 12.5 7C12.5 10.0376 10.0376 12.5 7 12.5C5.17893 12.5 3.58143 11.5907 2.62948 10.1875" />
          <path d="M1 4.5L1.5 7L4 5.5" />
        </svg>
      </button>

      <button
        onClick={() => setLiked(liked === true ? null : true)}
        className="p-1.5 rounded-md transition-opacity hover:opacity-80 cursor-pointer"
        style={{ color: liked === true ? "var(--accent-blue)" : "var(--text-muted)" }}
        title="Like"
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill={liked === true ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.5">
          <path d="M4 6V12H2.5C1.94772 12 1.5 11.5523 1.5 11V7C1.5 6.44772 1.94772 6 2.5 6H4ZM4 6L6 1.5C6.82843 1.5 7.5 2.17157 7.5 3V5H11.0656C11.6672 5 12.1305 5.52223 12.0592 6.11952L11.3092 12.1195C11.2486 12.6299 10.8132 13 10.2992 13H5.5C4.94772 13 4.5 12.5523 4.5 12" />
        </svg>
      </button>

      <button
        onClick={() => setLiked(liked === false ? null : false)}
        className="p-1.5 rounded-md transition-opacity hover:opacity-80 cursor-pointer"
        style={{ color: liked === false ? "var(--accent-red)" : "var(--text-muted)" }}
        title="Dislike"
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill={liked === false ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.5" className="rotate-180">
          <path d="M4 6V12H2.5C1.94772 12 1.5 11.5523 1.5 11V7C1.5 6.44772 1.94772 6 2.5 6H4ZM4 6L6 1.5C6.82843 1.5 7.5 2.17157 7.5 3V5H11.0656C11.6672 5 12.1305 5.52223 12.0592 6.11952L11.3092 12.1195C11.2486 12.6299 10.8132 13 10.2992 13H5.5C4.94772 13 4.5 12.5523 4.5 12" />
        </svg>
      </button>

      <button
        className="p-1.5 rounded-md transition-opacity hover:opacity-80 cursor-pointer"
        style={{ color: "var(--text-muted)" }}
        title="Share"
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
          <circle cx="10.5" cy="2.5" r="1.5" />
          <circle cx="3.5" cy="7" r="1.5" />
          <circle cx="10.5" cy="11.5" r="1.5" />
          <path d="M5 6L9 3.5M5 8L9 10.5" />
        </svg>
      </button>
    </div>
  );
}
