/**
 * FOTA 诊断平台 — 主页面组件
 *
 * 这是应用的核心页面，实现了完整的诊断对话流程：
 * 1. 场景选择：支持多种诊断场景切换
 * 2. 消息管理：维护用户和助手的对话历史
 * 3. SSE 流式处理：实时接收和展示诊断过程
 * 4. 状态管理：处理加载、流式输出、错误等状态
 *
 * 主要功能：
 * - 实时流式显示 Agent 执行过程（Thinking Process）
 * - 支持中断正在进行的诊断
 * - 自动滚动到最新消息
 * - 场景切换时清空对话历史
 *
 * @author FOTA 诊断平台团队
 * @created 2025
 * @updated 2025
 */

"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import Header from "@/components/Header";
import WelcomePage from "@/components/WelcomePage";
import InputBar from "@/components/InputBar";
import ChatMessageComponent from "@/components/ChatMessage";
import {
  DemoScenario,
  DEMO_SCENARIOS,
  ChatMessage,
  AgentStep,
} from "@/lib/types";
import { parseSSEBuffer } from "@/lib/sseParse";
import { rememberLastParseTaskId } from "@/components/TaskStatusLookup";


/**
 * SSE 事件载荷类型定义
 *
 * 定义了后端通过 SSE 推送的各种事件类型
 */
type SsePayload = {
  type: string;
  step?: AgentStep;
  stepNumber?: number;
  partialResult?: string;
  content?: string;
  sources?: ChatMessage["sources"];
  confidenceLevel?: ChatMessage["confidenceLevel"];
  // workspace_update fields
  file?: "notes.md" | "todo.md" | "focus.md";
  agent?: string;
  change?: string;
};

/**
 * 主页面组件
 *
 * 管理整个诊断对话的状态和交互逻辑
 */
export default function Home() {
  const [currentScenario, setCurrentScenario] = useState<DemoScenario>(
    DEMO_SCENARIOS[0]
  );
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<{
    active: boolean;
    percent: number;
    stage: string;
    message: string;
  }>({
    active: false,
    percent: 0,
    stage: "",
    message: "",
  });
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const handleScenarioChange = (scenario: DemoScenario) => {
    setCurrentScenario(scenario);
    setMessages([]);
    setIsRunning(false);
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  };

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setIsRunning(false);
    setMessages((prev) =>
      prev.map((m) => (m.isStreaming ? { ...m, isStreaming: false } : m))
    );
  };

  const handleUploadFiles = async (files: FileList | File[]) => {
    const fileArray = Array.from(files);
    if (fileArray.length === 0) return;

    const resultLines: string[] = [];
    const parseTaskActions: { label: string; taskId: string }[] = [];
    for (const file of fileArray) {
      const form = new FormData();
      form.append("file", file);
      form.append("case_id", currentScenario.id);

      try {
        setUploadProgress({
          active: true,
          percent: 3,
          stage: "uploading",
          message: `正在上传 ${file.name}`,
        });
        const resp = await fetch("/api/upload-log", {
          method: "POST",
          body: form,
        });
        const payload = await resp.json();
        if (!resp.ok) {
          resultLines.push(`- ${file.name}: 上传失败 (${payload?.detail || payload?.error || resp.status})`);
          continue;
        }
        const taskId = payload?.task_id;
        if (!taskId) {
          resultLines.push(`- ${file.name}: 提交任务失败（未返回 task_id）`);
          continue;
        }
        rememberLastParseTaskId(taskId);
        parseTaskActions.push({ label: file.name, taskId });

        let finalStatus: {
          status?: string;
          error?: string;
          result?: {
            total_files?: number;
            parsed_files?: number;
            total_events?: number;
            alignment_status?: string;
          };
          progress?: {
            percent?: number;
            stage?: string;
            message?: string;
          };
        } | null = null;
        for (let i = 0; i < 240; i += 1) {
          await new Promise((r) => setTimeout(r, 1000));
          const stResp = await fetch(`/api/parse-status/${taskId}`);
          const stPayload = await stResp.json();
          const p = stPayload?.progress;
          if (p) {
            setUploadProgress({
              active: true,
              percent: Number(p.percent ?? 0),
              stage: String(p.stage ?? "running"),
              message: String(p.message ?? "处理中"),
            });
          } else {
            setUploadProgress({
              active: true,
              percent: 20,
              stage: stPayload?.status || "running",
              message: "处理中",
            });
          }
          if (stPayload?.status === "completed" || stPayload?.status === "failed") {
            finalStatus = stPayload;
            break;
          }
        }

        if (!finalStatus) {
          resultLines.push(
            `- ${file.name}: 界面等待已结束，任务可能仍在后台处理，可点下方按钮查看实时状态。`
          );
          continue;
        }

        if (finalStatus.status === "failed") {
          resultLines.push(`- ${file.name}: 处理失败 (${finalStatus?.error || "unknown error"})`);
          continue;
        }

        const data = finalStatus?.result || {};
        resultLines.push(
          `- ${file.name}: 完成（解压文件 ${data.total_files ?? 0}，解析文件 ${data.parsed_files ?? 0}，事件 ${data.total_events ?? 0}，对齐 ${data.alignment_status ?? "UNKNOWN"}）`
        );
      } catch (err) {
        resultLines.push(`- ${file.name}: 上传异常 (${(err as Error).message})`);
      }
    }
    setUploadProgress({
      active: false,
      percent: 100,
      stage: "completed",
      message: "上传处理完成",
    });

    const uploadMessage: ChatMessage = {
      id: `${Date.now()}-upload`,
      role: "assistant",
      content: `日志上传处理结果：\n${resultLines.join("\n")}`,
      timestamp: new Date(),
      ...(parseTaskActions.length > 0 ? { parseTaskActions } : {}),
    };
    setMessages((prev) => [...prev, uploadMessage]);
  };

  const handleSend = async (message: string) => {
    if (isRunning) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: "user",
      content: message,
      timestamp: new Date(),
    };

    const assistantId = (Date.now() + 1).toString();
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      thinking: { steps: [], isExpanded: true },
      timestamp: new Date(),
      isStreaming: true,
    };

    setMessages((prev) => [...prev, userMessage, assistantMessage]);
    setIsRunning(true);

    const historyPayload = messages.map((m) => ({
      role: m.role,
      content: m.content,
    }));

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const applySsePayload = (data: SsePayload) => {
      switch (data.type) {
        case "step_start":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    thinking: {
                      ...m.thinking!,
                      steps: [...m.thinking!.steps, data.step as AgentStep],
                    },
                  }
                : m
            )
          );
          break;

        case "step_progress":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    thinking: {
                      ...m.thinking!,
                      steps: m.thinking!.steps.map((s) =>
                        s.stepNumber === data.stepNumber
                          ? { ...s, result: data.partialResult }
                          : s
                      ),
                    },
                  }
                : m
            )
          );
          break;

        case "step_complete":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    thinking: {
                      ...m.thinking!,
                      steps: m.thinking!.steps.map((s) =>
                        s.stepNumber === data.step?.stepNumber
                          ? (data.step as AgentStep)
                          : s
                      ),
                    },
                  }
                : m
            )
          );
          break;

        case "content_delta":
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== assistantId) return m;
              const chunk = data.content ?? "";
              const next =
                m.content === ""
                  ? chunk.replace(/^\n+/, "")
                  : m.content + chunk;
              return { ...m, content: next };
            })
          );
          break;

        case "content_complete":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    ...(data.content ? { content: data.content } : {}),
                    sources: data.sources,
                    confidenceLevel: data.confidenceLevel,
                    isStreaming: false,
                    thinking: {
                      ...m.thinking!,
                      isExpanded: false,
                    },
                  }
                : m
            )
          );
          break;

        case "workspace_update": {
          // Accumulate workspace updates onto the matching agent step
          const wsUpdate = {
            file: data.file ?? "notes.md",
            agent: data.agent ?? "",
            change: data.change ?? "",
            timestamp: new Date().toISOString(),
          } as import("@/lib/types").WorkspaceUpdate;

          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== assistantId) return m;
              const updatedSteps = m.thinking!.steps.map((s) => {
                if (s.agentName !== data.agent) return s;
                return {
                  ...s,
                  workspaceUpdates: [...(s.workspaceUpdates ?? []), wsUpdate],
                };
              });
              return { ...m, thinking: { ...m.thinking!, steps: updatedSteps } };
            })
          );
          break;
        }

        case "done":
          setIsRunning(false);
          break;
      }
    };

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          scenarioId: currentScenario.id,
          history: historyPayload,
        }),
        signal: abortController.signal,
      });

      if (!response.body) return;

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (value) {
          buffer += decoder.decode(value, { stream: true });
        }
        if (done) {
          buffer += decoder.decode();
          const { events } = parseSSEBuffer(buffer);
          for (const evt of events) {
            applySsePayload(evt as SsePayload);
          }
          break;
        }
        const { events, rest } = parseSSEBuffer(buffer);
        buffer = rest;
        for (const evt of events) {
          applySsePayload(evt as SsePayload);
        }
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      console.error("Stream error:", err);
      setIsRunning(false);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                content: "抱歉，处理请求时出现错误。请重试。",
                isStreaming: false,
              }
            : m
        )
      );
    }
  };

  const hasMessages = messages.length > 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: "var(--bg-primary)" }}>
      <Header
        currentScenario={currentScenario}
        onScenarioChange={handleScenarioChange}
      />

      <main style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column" }}>
        {!hasMessages ? (
          <WelcomePage onQuestionClick={handleSend} />
        ) : (
          <div style={{ maxWidth: "48rem", margin: "0 auto", padding: "24px 16px", width: "100%" }}>
            {messages.map((msg) => (
              <ChatMessageComponent key={msg.id} message={msg} />
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </main>

      <InputBar
        onSend={handleSend}
        isRunning={isRunning}
        onStop={handleStop}
        onUploadFiles={handleUploadFiles}
        uploadProgress={uploadProgress}
      />
    </div>
  );
}
