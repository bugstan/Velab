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

    // 日志列表 API (前端路由)
    http.get('/api/logfiles', () => {
        return HttpResponse.json({
            total: 2,
            items: [
                {
                    file_id: 'f1',
                    case_id: 'demo_case_001',
                    original_filename: 'saicmaxus.log',
                    source_type: 'android',
                    parse_status: 'PENDING',
                    uploaded_at: '2026-04-13T00:00:00Z',
                },
                {
                    file_id: 'f2',
                    case_id: 'demo_case_002',
                    original_filename: 'MCU_test.txt',
                    source_type: 'mcu',
                    parse_status: 'PENDING',
                    uploaded_at: '2026-04-13T00:01:00Z',
                },
            ],
        })
    }),

    // 日志上传 API (前端路由)
    http.post('/api/logfiles/upload', async () => {
        return HttpResponse.json({
            file_id: 'f3',
            case_id: 'demo_case_001',
            original_filename: 'upload.log',
            file_size: 1024,
            source_type: 'android',
            storage_path: '/tmp/mock',
            parse_status: 'PENDING',
            uploaded_at: '2026-04-13T00:02:00Z',
        })
    }),

    // Case 创建 API (前端路由)
    http.post('/api/cases', async ({ request }) => {
        const body = await request.json() as { case_id?: string }
        return HttpResponse.json({
            id: 1,
            case_id: body.case_id ?? 'CASE_MOCK',
            vin: null,
            vehicle_model: null,
            issue_description: null,
            status: 'active',
            metadata: {},
            created_at: '2026-04-13T00:00:00Z',
            updated_at: '2026-04-13T00:00:00Z',
        }, { status: 201 })
    }),

    http.post('/api/parse/submit', async () => {
        return HttpResponse.json({
            task_id: 'task_mock_001',
            case_id: 'demo_case_001',
            status: 'pending',
            total_files: 1,
            parsed_files: 0,
            failed_files: 0,
            total_events: 0,
            created_at: '2026-04-13T00:00:00Z',
            updated_at: '2026-04-13T00:00:00Z',
        }, { status: 202 })
    }),

    http.get('/api/parse/status/:taskId', async () => {
        return HttpResponse.json({
            task_id: 'task_mock_001',
            status: 'completed',
            result: {
                total_files: 1,
                parsed_files: 1,
                failed_files: 0,
                total_events: 10,
            },
        })
    }),

    http.post('/api/parse/align-time/:caseId', async () => {
        return HttpResponse.json({
            success: true,
            message: 'Time alignment completed',
            data: {
                status: 'SUCCESS',
                aligned_sources: 3,
                total_events: 10,
            },
        })
    }),

    // 健康检查
    http.get(`${BACKEND_URL}/health`, () => {
        return HttpResponse.json({ status: 'ok' })
    }),
]
