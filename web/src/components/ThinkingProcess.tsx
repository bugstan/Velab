"use client";

import { useState } from "react";
import { AgentStep, WorkspaceUpdate } from "@/lib/types";

interface ThinkingProcessProps {
  steps: AgentStep[];
  defaultExpanded?: boolean;
}

function StepStatusIcon({ status }: { status: AgentStep["status"] }) {
  if (status === "running") {
    return (
      <div
        className="w-4 h-4 rounded-full border-2 border-t-transparent animate-spin flex-shrink-0"
        style={{ borderColor: "var(--accent-blue)", borderTopColor: "transparent" }}
      />
    );
  }
  if (status === "completed") {
    return (
      <div
        className="w-4 h-4 rounded-full flex items-center justify-center flex-shrink-0"
        style={{ background: "#238636" }}
      >
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="white" strokeWidth="1.5">
          <path d="M2 5L4 7L8 3" />
        </svg>
      </div>
    );
  }
  return (
    <div
      className="w-4 h-4 rounded-full flex-shrink-0"
      style={{ background: "var(--border-color)" }}
    />
  );
}

/** Renders a single workspace update line with icon based on file/change type */
function WorkspaceUpdateItem({ update }: { update: WorkspaceUpdate }) {
  const isTodo = update.file === "todo.md";
  const isCompleted = update.change.trim().startsWith("[x]");
  const isNote = update.file === "notes.md";

  // Icon selection
  let icon = "📝";
  if (isTodo && isCompleted) icon = "✅";
  else if (isTodo && !isCompleted) icon = "⬜";
  else if (isNote) icon = "🔍";

  // Strip markdown checklist markers for display
  const displayText = update.change
    .replace(/^\[x\]\s*/i, "")
    .replace(/^\[ \]\s*/, "")
    .trim();

  return (
    <div
      className="flex items-start gap-1.5 py-0.5 animate-fade-in"
      style={{ animationDuration: "0.25s" }}
    >
      <span className="text-xs mt-px flex-shrink-0">{icon}</span>
      <span
        className="text-xs leading-relaxed"
        style={{
          color: isCompleted ? "#3fb950" : "var(--text-muted)",
          textDecoration: "none",
        }}
      >
        {displayText}
      </span>
    </div>
  );
}

/** Collapsible workspace checklist panel shown under each step */
function WorkspacePanel({
  updates,
  agentName,
}: {
  updates: WorkspaceUpdate[];
  agentName: string;
}) {
  const [open, setOpen] = useState(true);
  if (updates.length === 0) return null;

  const todoUpdates = updates.filter((u) => u.file === "todo.md");
  const noteUpdates = updates.filter((u) => u.file === "notes.md");

  return (
    <div
      className="mt-2 rounded-lg overflow-hidden"
      style={{
        border: "1px solid var(--border-color)",
        background: "var(--bg-tertiary)",
      }}
    >
      {/* Header */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:opacity-80 transition-opacity"
        style={{ background: "transparent" }}
      >
        <svg
          width="10"
          height="10"
          viewBox="0 0 12 12"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          style={{ color: "var(--text-muted)" }}
          className={`transition-transform flex-shrink-0 ${open ? "rotate-180" : ""}`}
        >
          <path d="M3 4.5L6 7.5L9 4.5" />
        </svg>
        <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
          Workspace · {agentName}
        </span>
        <span
          className="ml-auto text-xs font-mono px-1.5 py-0.5 rounded"
          style={{
            background: "var(--bg-secondary)",
            color: "var(--accent-blue)",
          }}
        >
          {updates.length} update{updates.length !== 1 ? "s" : ""}
        </span>
      </button>

      {/* Body */}
      {open && (
        <div className="px-3 pb-2 pt-0.5">
          {/* Todo checklist items */}
          {todoUpdates.length > 0 && (
            <div className="mb-1.5">
              <div
                className="text-xs font-mono mb-1"
                style={{ color: "var(--text-muted)", opacity: 0.6 }}
              >
                todo.md
              </div>
              {todoUpdates.map((u, i) => (
                <WorkspaceUpdateItem key={`todo-${i}`} update={u} />
              ))}
            </div>
          )}

          {/* Notes snippets */}
          {noteUpdates.length > 0 && (
            <div>
              <div
                className="text-xs font-mono mb-1"
                style={{ color: "var(--text-muted)", opacity: 0.6 }}
              >
                notes.md
              </div>
              {noteUpdates.map((u, i) => (
                <WorkspaceUpdateItem key={`note-${i}`} update={u} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ThinkingProcess({
  steps,
  defaultExpanded = false,
}: ThinkingProcessProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  const allCompleted = steps.every((s) => s.status === "completed");
  const currentStep = steps.find((s) => s.status === "running");

  return (
    <div className="mb-3">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 text-sm font-medium transition-opacity hover:opacity-80 cursor-pointer"
        style={{ color: "var(--text-secondary)" }}
      >
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className={`transition-transform ${isExpanded ? "rotate-180" : ""}`}
        >
          <path d="M3 4.5L6 7.5L9 4.5" />
        </svg>
        Thinking process
        {!allCompleted && currentStep && (
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            — {currentStep.agentName}
          </span>
        )}
        {allCompleted && (
          <span className="text-xs" style={{ color: "#238636" }}>
            — Completed
          </span>
        )}
      </button>

      {isExpanded && (
        <div className="mt-3 ml-1 animate-slide-down">
          {steps.map((step) => (
            <div key={step.stepNumber} className="flex gap-3 mb-4 last:mb-0">
              {/* Timeline connector */}
              <div className="flex flex-col items-center">
                <StepStatusIcon status={step.status} />
                {step.stepNumber < steps.length && (
                  <div
                    className="w-0.5 flex-1 mt-1"
                    style={{ background: "var(--border-color)" }}
                  />
                )}
              </div>

              {/* Step content */}
              <div className="flex-1 pb-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className="text-xs font-mono"
                    style={{ color: "var(--text-muted)" }}
                  >
                    Step {step.stepNumber}:
                  </span>
                  <span
                    className="text-sm font-medium"
                    style={{ color: "var(--text-primary)" }}
                  >
                    {step.agentName}
                  </span>
                </div>

                <div className="text-xs mb-1" style={{ color: "var(--accent-blue)" }}>
                  {step.statusText}
                </div>

                {/* Agent result summary */}
                {step.result && (
                  <div
                    className="text-xs mt-2 p-3 rounded-lg whitespace-pre-wrap leading-relaxed"
                    style={{
                      background: "var(--bg-tertiary)",
                      color: "var(--text-secondary)",
                      borderLeft: "2px solid var(--accent-blue)",
                    }}
                  >
                    {step.result}
                  </div>
                )}

                {/* Workspace checklist panel (only shown when updates exist) */}
                {step.workspaceUpdates && step.workspaceUpdates.length > 0 && (
                  <WorkspacePanel
                    updates={step.workspaceUpdates}
                    agentName={step.agentName}
                  />
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
