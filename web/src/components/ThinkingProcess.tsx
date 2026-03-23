"use client";

import { useState } from "react";
import { AgentStep } from "@/lib/types";

interface ThinkingProcessProps {
  steps: AgentStep[];
  defaultExpanded?: boolean;
}

function StepStatusIcon({ status }: { status: AgentStep["status"] }) {
  if (status === "running") {
    return (
      <div className="w-4 h-4 rounded-full border-2 border-t-transparent animate-spin"
        style={{ borderColor: "var(--accent-blue)", borderTopColor: "transparent" }} />
    );
  }
  if (status === "completed") {
    return (
      <div className="w-4 h-4 rounded-full flex items-center justify-center"
        style={{ background: "#238636" }}>
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="white" strokeWidth="1.5">
          <path d="M2 5L4 7L8 3" />
        </svg>
      </div>
    );
  }
  return (
    <div className="w-4 h-4 rounded-full"
      style={{ background: "var(--border-color)" }} />
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
              <div className="flex flex-col items-center">
                <StepStatusIcon status={step.status} />
                {step.stepNumber < steps.length && (
                  <div className="w-0.5 flex-1 mt-1" style={{ background: "var(--border-color)" }} />
                )}
              </div>
              <div className="flex-1 pb-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                    Step {step.stepNumber}:
                  </span>
                  <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                    {step.agentName}
                  </span>
                </div>
                <div className="text-xs mb-1" style={{ color: "var(--accent-blue)" }}>
                  {step.statusText}
                </div>
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
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
