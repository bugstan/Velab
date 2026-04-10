/**
 * MSW (Mock Service Worker) 处理器
 * 
 * 模拟后端 API 响应，用于测试
 */

import { http, HttpResponse } from 'msw'

const BACKEND_URL = 'http://localhost:8000'

/**
 * SSE 事件生成器
 */
function createSSEResponse(events: Record<string, unknown>[]) {
    const encoder = new TextEncoder()
    const stream = new ReadableStream({
        start(controller) {
            events.forEach((event) => {
                const data = `data: ${JSON.stringify(event)}\n\n`
                controller.enqueue(encoder.encode(data))
            })
            controller.close()
        },
    })

    return new HttpResponse(stream, {
        headers: {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
        },
    })
}

/**
 * API 处理器
 */
export const handlers = [
    // 聊天 API
    http.post(`${BACKEND_URL}/chat`, async ({ request }) => {
        await request.json()

        // 模拟 SSE 响应
        const events = [
            {
                type: 'step_start',
                step: {
                    stepNumber: 1,
                    agentName: 'Log Analytics Agent',
                    status: 'running',
                    statusText: 'Analyzing logs...',
                },
            },
            {
                type: 'step_complete',
                step: {
                    stepNumber: 1,
                    agentName: 'Log Analytics Agent',
                    status: 'completed',
                    statusText: 'Analysis complete',
                    result: 'Found 3 relevant entries',
                },
            },
            {
                type: 'content_delta',
                content: 'Based on the analysis, ',
            },
            {
                type: 'content_delta',
                content: 'the issue is related to network connectivity.',
            },
            {
                type: 'content_complete',
                sources: [],
                confidenceLevel: 'high',
            },
            {
                type: 'done',
            },
        ]

        return createSSEResponse(events)
    }),

    // 健康检查
    http.get(`${BACKEND_URL}/health`, () => {
        return HttpResponse.json({ status: 'ok' })
    }),
]
