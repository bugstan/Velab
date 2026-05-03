"use client";

import { PRESET_QUESTIONS, PresetQuestion } from "@/lib/types";

interface WelcomePageProps {
  onQuestionClick: (question: string, scenarioId?: string) => void;
}

export default function WelcomePage({ onQuestionClick }: WelcomePageProps) {
  return (
    <div className="flex flex-col items-center justify-center flex-1 px-4 animate-fade-in">
      <h1
        className="text-2xl font-semibold mb-8"
        style={{ color: "var(--text-primary)" }}
      >
        What are you working on?
      </h1>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-2xl">
        {PRESET_QUESTIONS.map((q: PresetQuestion) => (
          <button
            key={q.id}
            onClick={() => onQuestionClick(q.text, q.scenarioId)}
            className="flex items-center gap-3 px-4 py-3.5 rounded-xl border text-left hover:border-opacity-60 transition-all group cursor-pointer"
            style={{
              background: "var(--bg-secondary)",
              borderColor: "var(--border-color)",
            }}
          >
            <span className="text-lg">{q.icon}</span>
            <span
              className="text-sm group-hover:opacity-100 transition-opacity"
              style={{ color: "var(--text-secondary)", opacity: 0.85 }}
            >
              {q.text}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
