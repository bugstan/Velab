export interface DemoScenario {
  id: string;
  name: string;
  description: string;
}

export interface AgentStep {
  stepNumber: number;
  agentName: string;
  status: "pending" | "running" | "completed";
  statusText: string;
  result?: string;
}

export interface ThinkingProcessData {
  steps: AgentStep[];
  isExpanded: boolean;
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
    text: "How to install air filters?",
    icon: "🔧",
  },
  {
    id: "q2",
    text: "How to connect to your phone?",
    icon: "📱",
  },
  {
    id: "q3",
    text: "How to turn on the comfort driving mode?",
    icon: "🚗",
  },
  {
    id: "q4",
    text: "How to read vehicle signals or alerts?",
    icon: "📊",
  },
];
