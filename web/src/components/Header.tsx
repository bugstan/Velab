"use client";

import { useState, useRef, useEffect } from "react";
import { DemoScenario, DEMO_SCENARIOS } from "@/lib/types";

interface HeaderProps {
  currentScenario: DemoScenario;
  onScenarioChange: (scenario: DemoScenario) => void;
}

export default function Header({
  currentScenario,
  onScenarioChange,
}: HeaderProps) {
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <header className="sticky top-0 z-50 flex items-center justify-between px-4 py-3 border-b"
      style={{ borderColor: "var(--border-color)", background: "var(--bg-primary)" }}>
      <div className="flex items-center gap-3" ref={dropdownRef}>
        <div className="w-8 h-8 rounded-full flex items-center justify-center"
          style={{ background: "var(--accent-red)" }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
          </svg>
        </div>

        <div className="relative">
          <button
            onClick={() => setIsDropdownOpen(!isDropdownOpen)}
            className="flex items-center gap-2 text-sm font-medium hover:opacity-80 transition-opacity cursor-pointer"
            style={{ color: "var(--text-primary)" }}
          >
            {currentScenario.name}
            <svg
              width="12"
              height="12"
              viewBox="0 0 12 12"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className={`transition-transform ${isDropdownOpen ? "rotate-180" : ""}`}
            >
              <path d="M3 4.5L6 7.5L9 4.5" />
            </svg>
          </button>

          {isDropdownOpen && (
            <div
              className="absolute top-full left-0 mt-2 w-80 rounded-lg border shadow-xl py-1 animate-fade-in"
              style={{
                background: "var(--bg-secondary)",
                borderColor: "var(--border-color)",
              }}
            >
              {DEMO_SCENARIOS.map((scenario) => (
                <button
                  key={scenario.id}
                  onClick={() => {
                    onScenarioChange(scenario);
                    setIsDropdownOpen(false);
                  }}
                  className="w-full text-left px-4 py-2.5 flex items-center justify-between hover:opacity-80 transition-opacity cursor-pointer"
                  style={{
                    background:
                      scenario.id === currentScenario.id
                        ? "var(--bg-tertiary)"
                        : "transparent",
                    color: "var(--text-primary)",
                  }}
                >
                  <div>
                    <div className="text-sm font-medium">{scenario.name}</div>
                    <div
                      className="text-xs mt-0.5"
                      style={{ color: "var(--text-secondary)" }}
                    >
                      {scenario.description}
                    </div>
                  </div>
                  {scenario.id === currentScenario.id && (
                    <svg
                      width="16"
                      height="16"
                      viewBox="0 0 16 16"
                      fill="none"
                      stroke="var(--accent-blue)"
                      strokeWidth="2"
                    >
                      <path d="M3 8L7 12L13 4" />
                    </svg>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          className="text-sm px-3 py-1.5 rounded-md hover:opacity-80 transition-opacity cursor-pointer"
          style={{ color: "var(--text-secondary)" }}
        >
          Sign up
        </button>
        <button
          className="text-sm px-4 py-1.5 rounded-md font-medium transition-opacity hover:opacity-90 cursor-pointer"
          style={{ background: "var(--accent-blue)", color: "#fff" }}
        >
          Log in
        </button>
      </div>
    </header>
  );
}
