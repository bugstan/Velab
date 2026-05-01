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

    // 聊天 API (前端路由)
    http.post('/api/chat', async () => {
        const events = [
            { type: 'content_delta', content: 'Mock response from MSW' },
            { type: 'done' }
        ]
        return createSSEResponse(events)
    }),

    // 会话列表
    http.get('/api/sessions', () => {
        return HttpResponse.json([])
    }),

    // 会话更新
    http.put('/api/sessions/:sessionId', () => {
        return HttpResponse.json({})
    }),

    // 会话删除
    http.delete('/api/sessions/:sessionId', () => {
        return new HttpResponse(null, { status: 204 })
    }),

    // 标题生成
    http.post('/api/session-title', () => {
        return HttpResponse.json({ title: 'MSW 标题' })
    }),

    // 上传日志
    http.post('/api/upload-log', () => {
        return HttpResponse.json({ bundle_id: 'mock-bundle-id' })
    }),

    // bundle 状态查询
    http.get('/api/bundle-status/:bundleId', () => {
        return HttpResponse.json({ status: 'done', progress: 1 })
    }),

    // 健康检查
    http.get(`${BACKEND_URL}/health`, () => {
        return HttpResponse.json({ status: 'ok' })
    }),
]
