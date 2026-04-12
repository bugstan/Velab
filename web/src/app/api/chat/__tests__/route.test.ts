/**
 * API 路由测试
 *
 * 测试 /api/chat 端点的功能
 */

import { POST } from '@/app/api/chat/route'
import { NextRequest } from 'next/server'
import { vi, beforeEach, afterEach, describe, it, expect } from 'vitest'

describe('API Route: /api/chat', () => {
    let mockFetch: ReturnType<typeof vi.fn>

    beforeEach(() => {
        // 为每个测试创建新的 fetch spy
        mockFetch = vi.fn()
        vi.stubGlobal('fetch', mockFetch)
    })

    afterEach(() => {
        vi.unstubAllGlobals()
    })

    describe('成功响应', () => {
        it('应该转发请求到后端', async () => {
            const mockStream = new ReadableStream({
                start(controller) {
                    controller.enqueue(new TextEncoder().encode('data: {"type":"test"}\n\n'))
                    controller.close()
                },
            })

            mockFetch.mockResolvedValue({
                ok: true,
                body: mockStream,
            })

            const request = new NextRequest('http://localhost:3000/api/chat', {
                method: 'POST',
                body: JSON.stringify({
                    message: 'Test message',
                    scenarioId: 'test-scenario',
                    history: [],
                }),
            })

            const response = await POST(request)

            expect(mockFetch).toHaveBeenCalledWith(
                expect.stringContaining('/chat'),
                expect.objectContaining({
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                })
            )

            expect(response.headers.get('Content-Type')).toBe('text/event-stream')
        })

        it('应该返回 SSE 流', async () => {
            const mockStream = new ReadableStream({
                start(controller) {
                    controller.enqueue(new TextEncoder().encode('data: {"type":"content_delta","content":"Test"}\n\n'))
                    controller.close()
                },
            })

            mockFetch.mockResolvedValue({
                ok: true,
                body: mockStream,
            })

            const request = new NextRequest('http://localhost:3000/api/chat', {
                method: 'POST',
                body: JSON.stringify({
                    message: 'Test',
                    scenarioId: 'test',
                    history: [],
                }),
            })

            const response = await POST(request)

            expect(response.headers.get('Content-Type')).toBe('text/event-stream')
            expect(response.headers.get('Cache-Control')).toBe('no-cache')
            expect(response.headers.get('Connection')).toBe('keep-alive')
        })
    })

    describe('错误处理', () => {
        it('应该处理后端错误响应', async () => {
            mockFetch.mockResolvedValue({
                ok: false,
                status: 500,
            })

            const request = new NextRequest('http://localhost:3000/api/chat', {
                method: 'POST',
                body: JSON.stringify({
                    message: 'Test',
                    scenarioId: 'test',
                    history: [],
                }),
            })

            const response = await POST(request)

            expect(response.status).toBe(500)
            const body = await response.json()
            expect(body).toHaveProperty('error')
        })

        it('应该处理空响应体', async () => {
            mockFetch.mockResolvedValue({
                ok: true,
                body: null,
            })

            const request = new NextRequest('http://localhost:3000/api/chat', {
                method: 'POST',
                body: JSON.stringify({
                    message: 'Test',
                    scenarioId: 'test',
                    history: [],
                }),
            })

            const response = await POST(request)

            expect(response.status).toBe(502)
            const body = await response.json()
            expect(body.error).toBe('No response body')
        })

        it('应该处理网络错误', async () => {
            mockFetch.mockRejectedValue(new Error('Network error'))

            const request = new NextRequest('http://localhost:3000/api/chat', {
                method: 'POST',
                body: JSON.stringify({
                    message: 'Test',
                    scenarioId: 'test',
                    history: [],
                }),
            })

            const response = await POST(request)

            expect(response.status).toBe(504)
            const body = await response.json()
            expect(body.error).toBe('Network error')
        })

        it('应该处理超时', async () => {
            // 模拟 AbortController 超时错误
            const abortError = new Error('The operation was aborted')
            abortError.name = 'AbortError'
            
            mockFetch.mockRejectedValue(abortError)

            const request = new NextRequest('http://localhost:3000/api/chat', {
                method: 'POST',
                body: JSON.stringify({
                    message: 'Test',
                    scenarioId: 'test',
                    history: [],
                }),
            })

            const response = await POST(request)

            expect(response.status).toBe(504)
            const body = await response.json()
            expect(body.error).toBe('The operation was aborted')
        })
    })

    describe('请求验证', () => {
        it('应该接受有效的请求体', async () => {
            const mockStream = new ReadableStream()

            mockFetch.mockResolvedValue({
                ok: true,
                body: mockStream,
            })

            const request = new NextRequest('http://localhost:3000/api/chat', {
                method: 'POST',
                body: JSON.stringify({
                    message: 'Valid message',
                    scenarioId: 'valid-scenario',
                    history: [
                        { role: 'user', content: 'Previous message' },
                        { role: 'assistant', content: 'Previous response' },
                    ],
                }),
            })

            await POST(request)

            expect(mockFetch).toHaveBeenCalled()
        })

        it('应该转发完整的请求体', async () => {
            const mockStream = new ReadableStream()

            mockFetch.mockResolvedValue({
                ok: true,
                body: mockStream,
            })

            const requestBody = {
                message: 'Test message',
                scenarioId: 'test-scenario',
                history: [{ role: 'user', content: 'Previous' }],
            }

            const request = new NextRequest('http://localhost:3000/api/chat', {
                method: 'POST',
                body: JSON.stringify(requestBody),
            })

            await POST(request)

            expect(mockFetch).toHaveBeenCalledWith(
                expect.any(String),
                expect.objectContaining({
                    body: JSON.stringify(requestBody),
                })
            )
        })
    })

    describe('边界情况', () => {
        it('应该处理空消息', async () => {
            const mockStream = new ReadableStream()

            mockFetch.mockResolvedValue({
                ok: true,
                body: mockStream,
            })

            const request = new NextRequest('http://localhost:3000/api/chat', {
                method: 'POST',
                body: JSON.stringify({
                    message: '',
                    scenarioId: 'test',
                    history: [],
                }),
            })

            await POST(request)

            expect(mockFetch).toHaveBeenCalled()
        })

        it('应该处理长消息', async () => {
            const mockStream = new ReadableStream()

            mockFetch.mockResolvedValue({
                ok: true,
                body: mockStream,
            })

            const longMessage = 'A'.repeat(10000)

            const request = new NextRequest('http://localhost:3000/api/chat', {
                method: 'POST',
                body: JSON.stringify({
                    message: longMessage,
                    scenarioId: 'test',
                    history: [],
                }),
            })

            await POST(request)

            expect(mockFetch).toHaveBeenCalled()
        })

        it('应该处理大量历史记录', async () => {
            const mockStream = new ReadableStream()

            mockFetch.mockResolvedValue({
                ok: true,
                body: mockStream,
            })

            const largeHistory = Array(100).fill(null).map((_, i) => ({
                role: i % 2 === 0 ? 'user' : 'assistant',
                content: `Message ${i}`,
            }))

            const request = new NextRequest('http://localhost:3000/api/chat', {
                method: 'POST',
                body: JSON.stringify({
                    message: 'Test',
                    scenarioId: 'test',
                    history: largeHistory,
                }),
            })

            await POST(request)

            expect(mockFetch).toHaveBeenCalled()
        })
    })
})
