/**
 * 测试数据 Mock
 * 
 * 提供测试中使用的模拟数据
 */

import {
    ChatMessage,
    AgentStep,
    DemoScenario,
    PresetQuestion,
} from '@/lib/types'

/**
 * Mock Agent 步骤
 */
export const mockAgentSteps: AgentStep[] = [
    {
        stepNumber: 1,
        agentName: 'Log Analytics Agent',
        status: 'completed',
        statusText: 'Analyzing FOTA logs...',
        result: 'Found 3 relevant log entries',
    },
    {
        stepNumber: 2,
        agentName: 'Jira Knowledge Agent',
        status: 'running',
        statusText: 'Searching Jira tickets...',
    },
    {
        stepNumber: 3,
        agentName: 'Orchestrator',
        status: 'pending',
        statusText: 'Waiting...',
    },
]

/**
 * Mock 用户消息
 */
export const mockUserMessage: ChatMessage = {
    id: '1',
    role: 'user',
    content: 'What is causing the FOTA update failure?',
    timestamp: new Date('2025-01-01T10:00:00Z'),
}

/**
 * Mock 助手消息（无 Thinking Process）
 */
export const mockAssistantMessage: ChatMessage = {
    id: '2',
    role: 'assistant',
    content: 'Based on the logs, the FOTA update failure is caused by...',
    timestamp: new Date('2025-01-01T10:00:05Z'),
}

/**
 * Mock 助手消息（带 Thinking Process）
 */
export const mockAssistantMessageWithThinking: ChatMessage = {
    id: '3',
    role: 'assistant',
    content: '## Analysis Results\n\nThe issue is related to network connectivity.',
    thinking: {
        steps: mockAgentSteps,
        isExpanded: true,
    },
    timestamp: new Date('2025-01-01T10:00:10Z'),
}

/**
 * Mock 流式消息
 */
export const mockStreamingMessage: ChatMessage = {
    id: '4',
    role: 'assistant',
    content: 'Analyzing...',
    isStreaming: true,
    thinking: {
        steps: [mockAgentSteps[0]],
        isExpanded: true,
    },
    timestamp: new Date('2025-01-01T10:00:15Z'),
}

/**
 * Mock 场景
 */
export const mockScenario: DemoScenario = {
    id: 'test-scenario',
    name: 'Test Scenario',
    description: 'A test scenario for unit tests',
}

/**
 * Mock 预设问题
 */
export const mockPresetQuestions: PresetQuestion[] = [
    {
        id: 'q1',
        text: 'Test question 1',
        icon: '🔧',
    },
    {
        id: 'q2',
        text: 'Test question 2',
        icon: '📱',
    },
]

/**
 * Mock Markdown 内容
 */
export const mockMarkdownContent = `
## Heading 2

### Heading 3

This is a paragraph with **bold text** and \`inline code\`.

- List item 1
- List item 2
- List item 3

1. Ordered item 1
2. Ordered item 2

\`\`\`
code block
multiple lines
\`\`\`

| Column 1 | Column 2 |
|----------|----------|
| Cell 1   | Cell 2   |
| Cell 3   | Cell 4   |

---

[Link text](https://example.com)
`
