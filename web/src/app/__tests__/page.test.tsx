/**
 * 主页面集成测试
 *
 * 测试主页面的完整功能流程
 */

import { render, screen, waitFor } from '@/__tests__/utils/test-utils'
import Home from '@/app/page'
import userEvent from '@testing-library/user-event'
import { DEMO_SCENARIOS, PRESET_QUESTIONS } from '@/lib/types'
import { vi, describe, it, beforeEach, expect } from 'vitest'

// Mock fetch for SSE
const mockFetch = vi.fn()
global.fetch = mockFetch as unknown as typeof fetch

const createSseResponse = (chunks: string[]) => {
    const encodedChunks = chunks.map((chunk) => new TextEncoder().encode(chunk))
    const queue = [...encodedChunks]
    const reader = {
        read: vi.fn().mockImplementation(async () => {
            if (queue.length === 0) {
                return { done: true, value: undefined }
            }
            return { done: false, value: queue.shift() }
        }),
    }
    return {
        ok: true,
        body: {
            getReader: () => reader,
        },
    }
}

const setupFetchMock = (chatResponse?: unknown, sessions: unknown[] = []) => {
    mockFetch.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string'
            ? input
            : input instanceof URL
                ? input.toString()
                : input.url
        const method = (init?.method || 'GET').toUpperCase()

        if (url.includes('/api/sessions') && method === 'GET') {
            return {
                ok: true,
                json: async () => sessions,
            } as Response
        }

        if (url.includes('/api/sessions/') && method === 'PUT') {
            return {
                ok: true,
                json: async () => ({}),
            } as Response
        }

        if (url.includes('/api/sessions/') && method === 'DELETE') {
            return {
                ok: true,
                status: 204,
                json: async () => ({}),
            } as Response
        }

        if (chatResponse) {
            return chatResponse as Response
        }
        return createSseResponse([]) as unknown as Response
    })
}

describe('Home Page Integration Tests', () => {
    beforeEach(() => {
        vi.clearAllMocks()
        mockFetch.mockClear()
        window.localStorage.clear()
        setupFetchMock()
    })

    describe('初始渲染', () => {
        it('应该渲染 Header 组件', () => {
            render(<Home />)

            expect(screen.getByText(DEMO_SCENARIOS[0].name)).toBeInTheDocument()
        })

        it('应该渲染 WelcomePage', () => {
            render(<Home />)

            expect(screen.getByText('What are you working on?')).toBeInTheDocument()
        })

        it('应该渲染 InputBar', () => {
            render(<Home />)

            expect(screen.getByPlaceholderText('Ask a question')).toBeInTheDocument()
        })

        it('不应渲染 Bundle 摄取状态面板', () => {
            render(<Home />)

            expect(screen.queryByText('Bundle 摄取状态')).not.toBeInTheDocument()
        })

        it('应该显示所有预设问题', () => {
            render(<Home />)

            PRESET_QUESTIONS.forEach(question => {
                expect(screen.getByText(question.text)).toBeInTheDocument()
            })
        })

    })

    describe('发送消息流程', () => {
        it('点击预设问题应该发送消息', async () => {
            const user = userEvent.setup()

            setupFetchMock(
                createSseResponse([
                    'data: {"type":"content_delta","content":"Test"}\n\n',
                ])
            )

            render(<Home />)

            const firstQuestion = PRESET_QUESTIONS[0]
            const questionButton = screen.getByText(firstQuestion.text)

            await user.click(questionButton)

            // 应该显示用户消息
            await waitFor(() => {
                expect(screen.getAllByText(firstQuestion.text).length).toBeGreaterThan(0)
            })
        })

        it('通过输入框发送消息', async () => {
            const user = userEvent.setup()

            setupFetchMock(
                createSseResponse([
                    'data: {"type":"content_delta","content":"Response"}\n\n',
                ])
            )

            render(<Home />)

            const input = screen.getByPlaceholderText('Ask a question')
            const runButton = screen.getByText('Run')

            await user.type(input, 'Test question')
            await user.click(runButton)

            // 应该显示用户消息
            await waitFor(() => {
                expect(screen.getAllByText('Test question').length).toBeGreaterThan(0)
            })
        })

        it('发送消息后应该隐藏 WelcomePage', async () => {
            const user = userEvent.setup()

            setupFetchMock(createSseResponse([]))

            render(<Home />)

            const input = screen.getByPlaceholderText('Ask a question')
            await user.type(input, 'Test{Enter}')

            // WelcomePage 应该消失
            await waitFor(() => {
                expect(screen.queryByText('What are you working on?')).not.toBeInTheDocument()
            })
        })
    })

    describe('场景切换', () => {
        it('切换场景不应清空当前会话消息', async () => {
            const user = userEvent.setup()

            setupFetchMock(createSseResponse([]))

            render(<Home />)

            // 发送消息
            const input = screen.getByPlaceholderText('Ask a question')
            await user.type(input, 'Test message{Enter}')

            await waitFor(() => {
                expect(screen.getAllByText('Test message').length).toBeGreaterThan(0)
            })

            // 切换场景
            const scenarioButton = screen.getByRole('button', { name: new RegExp(DEMO_SCENARIOS[0].name) })
            await user.click(scenarioButton)

            const nextScenario = screen.getByText(DEMO_SCENARIOS[1].name)
            await user.click(nextScenario)

            // 当前会话消息应保留
            await waitFor(() => {
                expect(screen.getAllByText('Test message').length).toBeGreaterThan(0)
            })
        })
    })

    describe('Stop 功能', () => {
        it.skip('运行中应该显示 Stop 按钮', async () => {
            const user = userEvent.setup()

            // Mock 一个持续流式响应的流
            let readCount = 0
            const mockReader = {
                read: vi.fn().mockImplementation(() => {
                    readCount++
                    if (readCount === 1) {
                        return Promise.resolve({
                            done: false,
                            value: new TextEncoder().encode('data: {"type":"content_delta","content":"Test"}\n\n'),
                        })
                    }
                    // 后续调用永不resolve，保持流打开状态
                    return new Promise(() => { })
                }),
            }

            mockFetch.mockResolvedValue({
                ok: true,
                body: {
                    getReader: () => mockReader,
                },
            })

            render(<Home />)

            const input = screen.getByPlaceholderText('Ask a question')
            
            // 发送消息
            await user.type(input, 'Test{Enter}')

            // 等待用户消息显示
            await waitFor(() => {
                expect(screen.getByText('Test')).toBeInTheDocument()
            }, { timeout: 1000 })

            // 应该显示 Stop 按钮（isRunning为true时）
            await waitFor(() => {
                expect(screen.getByText('Stop')).toBeInTheDocument()
            }, { timeout: 3000 })
        })
    })

    describe('错误处理', () => {
        it.skip('应该处理网络错误', async () => {
            const user = userEvent.setup()

            mockFetch.mockRejectedValue(new Error('Network error'))

            render(<Home />)

            const input = screen.getByPlaceholderText('Ask a question')
            await user.type(input, 'Test{Enter}')

            // 等待用户消息显示
            await waitFor(() => {
                expect(screen.getByText('Test')).toBeInTheDocument()
            }, { timeout: 1000 })

            // 错误消息会显示在助手消息中
            await waitFor(() => {
                const errorMessage = screen.queryByText(/抱歉，处理请求时出现错误/)
                expect(errorMessage).toBeInTheDocument()
            }, { timeout: 3000 })
        })

        it.skip('应该处理 AbortError', async () => {
            const user = userEvent.setup()

            const abortError = new Error('Aborted')
            abortError.name = 'AbortError'

                mockFetch.mockRejectedValue(abortError)

            render(<Home />)

            const input = screen.getByPlaceholderText('Ask a question')
            await user.type(input, 'Test{Enter}')

            // AbortError 不应该显示错误消息
            await waitFor(() => {
                expect(screen.queryByText(/抱歉/)).not.toBeInTheDocument()
            })
        })
    })

    describe('消息渲染', () => {
        it.skip('应该渲染用户和助手消息', async () => {
            const user = userEvent.setup()

            const mockReader = {
                read: vi.fn()
                    .mockResolvedValueOnce({
                        done: false,
                        value: new TextEncoder().encode('data: {"type":"content_delta","content":"Assistant response"}\n\n'),
                    })
                    .mockResolvedValueOnce({
                        done: false,
                        value: new TextEncoder().encode('data: {"type":"done"}\n\n'),
                    })
                    .mockResolvedValueOnce({
                        done: true,
                        value: undefined,
                    }),
            }

            mockFetch.mockResolvedValue({
                ok: true,
                body: {
                    getReader: () => mockReader,
                },
            })

            render(<Home />)

            const input = screen.getByPlaceholderText('Ask a question')
            await user.type(input, 'User question{Enter}')

            // 应该显示用户消息
            await waitFor(() => {
                expect(screen.getByText('User question')).toBeInTheDocument()
            }, { timeout: 1000 })

            // 应该显示助手响应（等待流处理）
            await waitFor(() => {
                expect(screen.getByText(/Assistant response/)).toBeInTheDocument()
            }, { timeout: 3000 })

            // 验证流已完成
            await waitFor(() => {
                expect(mockReader.read).toHaveBeenCalled()
            }, { timeout: 1000 })
        })
    })

    describe('自动滚动', () => {
        it('新消息应该触发滚动', async () => {
            const user = userEvent.setup()

            // 创建 scrollIntoView 的 spy
            const scrollIntoViewSpy = vi.fn()
            Element.prototype.scrollIntoView = scrollIntoViewSpy

            setupFetchMock(createSseResponse([]))

            render(<Home />)

            const input = screen.getByPlaceholderText('Ask a question')
            await user.type(input, 'Test{Enter}')

            // 等待消息显示
            await waitFor(() => {
                expect(screen.getAllByText('Test').length).toBeGreaterThan(0)
            })

            // scrollIntoView 应该被调用
            await waitFor(() => {
                expect(scrollIntoViewSpy).toHaveBeenCalled()
            }, { timeout: 2000 })
        })
    })

    describe('边界情况', () => {
        it('应该处理空响应体', async () => {
            const user = userEvent.setup()

            setupFetchMock({
                ok: true,
                body: null,
            } as Response)

            render(<Home />)

            const input = screen.getByPlaceholderText('Ask a question')
            await user.type(input, 'Test{Enter}')

            // 应该正常处理，不崩溃
            await waitFor(() => {
                expect(screen.getAllByText('Test').length).toBeGreaterThan(0)
            })
        })

        it.skip('应该处理多条连续消息', async () => {
            const user = userEvent.setup()

            let callCount = 0
            mockFetch.mockImplementation(() => {
                callCount++
                const mockReader = {
                    read: vi.fn()
                        .mockResolvedValueOnce({
                            done: false,
                            value: new TextEncoder().encode('data: {"type":"content_delta","content":"Response"}\n\n'),
                        })
                        .mockResolvedValueOnce({
                            done: false,
                            value: new TextEncoder().encode('data: {"type":"done"}\n\n'),
                        })
                        .mockResolvedValueOnce({
                            done: true,
                            value: undefined,
                        }),
                }

                return Promise.resolve({
                    ok: true,
                    body: {
                        getReader: () => mockReader,
                    },
                })
            })

            render(<Home />)

            const input = screen.getByPlaceholderText('Ask a question')

            // 发送第一条消息
            await user.type(input, 'Message 1{Enter}')
            await waitFor(() => expect(screen.getByText('Message 1')).toBeInTheDocument(), { timeout: 1000 })

            // 等待第一条消息完成（Run按钮重新出现）
            await waitFor(() => expect(screen.getByText('Run')).toBeInTheDocument(), { timeout: 5000 })

            // 清空输入框并发送第二条消息
            await user.clear(input)
            await user.type(input, 'Message 2{Enter}')
            await waitFor(() => expect(screen.getByText('Message 2')).toBeInTheDocument(), { timeout: 1000 })

            // 等待第二条消息完成
            await waitFor(() => expect(callCount).toBeGreaterThanOrEqual(2), { timeout: 5000 })
        })
    })
})
