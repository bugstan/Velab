export interface DemoScenario {
  id: string;
  name: string;
  description: string;
}

export interface WorkspaceUpdate {
  file: "notes.md" | "todo.md" | "focus.md";
  agent: string;
  change: string;          // e.g. "[x] 日志阶段验证完成" or "发现关联工单 FOTA-8765"
  timestamp: string;       // ISO 8601
}

export interface AgentStep {
  stepNumber: number;
  agentName: string;
  status: "pending" | "running" | "completed";
  statusText: string;
  result?: string;
  workspaceUpdates?: WorkspaceUpdate[];  // real-time checklist/notes updates
}

export interface ThinkingProcessData {
  steps: AgentStep[];
  isExpanded: boolean;
}

/** 与 log_pipeline bundle 摄取关联的快捷操作（在气泡内展示「查看状态」等） */
export interface BundleAction {
  label: string;
  bundleId: string;
  action?: "status" | "rangeQuery";
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  thinking?: ThinkingProcessData;
  timestamp: Date;
  isStreaming?: boolean;
  sources?: SourceReference[];
  confidenceLevel?: string;
  /** 有 bundle 摄取任务时展示跳转到底栏状态查询的按钮 */
  bundleActions?: BundleAction[];
}

export interface SourceReference {
  title: string;
  url?: string;
  type: "log" | "jira" | "document" | "pdf";
}

export interface PresetQuestion {
  id: string;
  text: string;
  icon: string;
}

export const DEMO_SCENARIOS: DemoScenario[] = [
  {
    id: "fota-diagnostic",
    name: "Maxus FOTA Diagnostic Demo",
    description: "基础 FOTA 诊断分析",
  },
  {
    id: "fota-jira",
    name: "Maxus FOTA Diagnostic with Jira Demo",
    description: "FOTA 诊断 + Jira 工单检索",
  },
  {
    id: "fleet-analytics",
    name: "Fleet Data Analytics Demo",
    description: "车队数据分析",
  },
  {
    id: "ces-demo",
    name: "CES Demo",
    description: "CES 展会演示",
  },
  {
    id: "data-acquisitions",
    name: "Data Acquisitions Demo",
    description: "数据采集演示",
  },
];

export const PRESET_QUESTIONS: PresetQuestion[] = [
  {
    id: "q1",
    text: "分析 FOTA 升级失败的根本原因",
    icon: "🔍",
  },
  {
    id: "q2",
    text: "查询类似 FOTA-9123 的历史案例",
    icon: "📋",
  },
  {
    id: "q3",
    text: "分析为何 iCGM 模块升级时挂死",
    icon: "⚠️",
  },
  {
    id: "q4",
    text: "MPU 升级包校验失败的常见原因",
    icon: "📦",
  },
];
