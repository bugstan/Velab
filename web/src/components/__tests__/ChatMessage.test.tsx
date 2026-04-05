/**
 * ChatMessage 组件测试
 *
 * 测试聊天消息组件的渲染和功能
 */

import { render, screen } from '@/__tests__/utils/test-utils'
import ChatMessageComponent from '@/components/ChatMessage'
import {
    mockUserMessage,
    mockAssistantMessage,
    mockAssistantMessageWithThinking,
    mockStreamingMessage,
} from '@/__tests__/mocks/data'
import { describe, it, expect } from 'vitest'

describe('ChatMessage Component', () => {
    describe('用户消息渲染', () => {
        it('应该正确渲染用户消息', () => {
            render(<ChatMessageComponent message={mockUserMessage} />)

            expect(screen.getByText(mockUserMessage.content)).toBeInTheDocument()
        })

        it('用户消息应该有正确的样式类', () => {
            const { container } = render(<ChatMessageComponent message={mockUserMessage} />)

            const messageDiv = container.querySelector('.justify-end')
            expect(messageDiv).toBeInTheDocument()
        })
    })

    describe('助手消息渲染', () => {
        it('应该正确渲染助手消息', () => {
            render(<ChatMessageComponent message={mockAssistantMessage} />)

            expect(screen.getByText(/Based on the logs/)).toBeInTheDocument()
        })

        it('应该显示 Technician 标签', () => {
            render(<ChatMessageComponent message={mockAssistantMessage} />)

            expect(screen.getByText('Technician')).toBeInTheDocument()
        })

        it('应该显示助手头像图标', () => {
            const { container } = render(<ChatMessageComponent message={mockAssistantMessage} />)

            const avatar = container.querySelector('svg')
            expect(avatar).toBeInTheDocument()
        })
    })

    describe('Markdown 渲染', () => {
        it('应该渲染标题', () => {
            const messageWithHeading = {
                ...mockAssistantMessage,
                content: '## Test Heading\n\nSome content',
            }

            const { container } = render(<ChatMessageComponent message={messageWithHeading} />)

            const heading = container.querySelector('h2')
            expect(heading).toBeInTheDocument()
            expect(heading?.textContent).toBe('Test Heading')
        })

        it('应该渲染粗体文本', () => {
            const messageWithBold = {
                ...mockAssistantMessage,
                content: 'This is **bold text**',
            }

            const { container } = render(<ChatMessageComponent message={messageWithBold} />)

            const strong = container.querySelector('strong')
            expect(strong).toBeInTheDocument()
            expect(strong?.textContent).toBe('bold text')
        })

        it('应该渲染行内代码', () => {
            const messageWithCode = {
                ...mockAssistantMessage,
                content: 'Use `console.log()` for debugging',
            }

            const { container } = render(<ChatMessageComponent message={messageWithCode} />)

            const code = container.querySelector('code')
            expect(code).toBeInTheDocument()
            expect(code?.textContent).toBe('console.log()')
        })

        it('应该渲染代码块', () => {
            const messageWithCodeBlock = {
                ...mockAssistantMessage,
                content: '```javascript\nconst x = 1;\nconsole.log(x);\n```',
            }

            const { container } = render(<ChatMessageComponent message={messageWithCodeBlock} />)

            // 代码块通过 dangerouslySetInnerHTML 渲染，需要在 markdown-content 中查找
            const markdownContent = container.querySelector('.markdown-content')
            expect(markdownContent).toBeInTheDocument()
            
            // 检查代码内容
            const textContent = markdownContent?.textContent || ''
            expect(textContent).toContain('const x = 1')
            expect(textContent).toContain('console.log(x)')
        })

        it('应该渲染无序列表', () => {
            const messageWithList = {
                ...mockAssistantMessage,
                content: '- Item 1\n- Item 2\n- Item 3',
            }

            const { container } = render(<ChatMessageComponent message={messageWithList} />)

            const ul = container.querySelector('ul')
            const listItems = container.querySelectorAll('li')

            expect(ul).toBeInTheDocument()
            expect(listItems).toHaveLength(3)
        })

        it('应该渲染有序列表', () => {
            const messageWithOrderedList = {
                ...mockAssistantMessage,
                content: '1. First\n2. Second\n3. Third',
            }

            const { container } = render(<ChatMessageComponent message={messageWithOrderedList} />)

            const ol = container.querySelector('ol')
            const listItems = container.querySelectorAll('li')

            expect(ol).toBeInTheDocument()
            expect(listItems).toHaveLength(3)
        })

        it('应该渲染链接', () => {
            const messageWithLink = {
                ...mockAssistantMessage,
                content: 'Visit [Google](https://google.com) for more info',
            }

            const { container } = render(<ChatMessageComponent message={messageWithLink} />)

            const link = container.querySelector('a')
            expect(link).toBeInTheDocument()
            expect(link?.getAttribute('href')).toBe('https://google.com')
            expect(link?.textContent).toBe('Google')
        })

        it('应该渲染表格', () => {
            const messageWithTable = {
                ...mockAssistantMessage,
                content: '| Col1 | Col2 |\n|------|------|\n| A | B |\n| C | D |',
            }

            const { container } = render(<ChatMessageComponent message={messageWithTable} />)

            const table = container.querySelector('table')
            const rows = container.querySelectorAll('tr')

            expect(table).toBeInTheDocument()
            expect(rows.length).toBeGreaterThan(0)
        })

        it('应该渲染分隔线', () => {
            const messageWithHr = {
                ...mockAssistantMessage,
                content: 'Before\n\n---\n\nAfter',
            }

            const { container } = render(<ChatMessageComponent message={messageWithHr} />)

            const hr = container.querySelector('hr')
            expect(hr).toBeInTheDocument()
        })
    })

    describe('Thinking Process', () => {
        it('应该渲染 Thinking Process 组件', () => {
            render(<ChatMessageComponent message={mockAssistantMessageWithThinking} />)

            expect(screen.getByText('Thinking process')).toBeInTheDocument()
        })

        it('没有 thinking 数据时不应该渲染 Thinking Process', () => {
            render(<ChatMessageComponent message={mockAssistantMessage} />)

            expect(screen.queryByText('Thinking process')).not.toBeInTheDocument()
        })
    })

    describe('流式输出', () => {
        it('流式消息应该显示光标动画', () => {
            const { container } = render(<ChatMessageComponent message={mockStreamingMessage} />)

            const streamingElement = container.querySelector('.streaming-cursor')
            expect(streamingElement).toBeInTheDocument()
        })

        it('流式消息不应该显示反馈按钮', () => {
            render(<ChatMessageComponent message={mockStreamingMessage} />)

            // 反馈按钮应该不存在（因为 isStreaming = true）
            const buttons = screen.queryAllByRole('button')
            // 只有 Thinking Process 的按钮，没有反馈按钮
            expect(buttons.length).toBeLessThanOrEqual(1)
        })

        it('非流式消息应该显示反馈按钮', () => {
            render(<ChatMessageComponent message={mockAssistantMessage} />)

            // 应该有多个按钮（反馈按钮组）
            const buttons = screen.getAllByRole('button')
            expect(buttons.length).toBeGreaterThan(0)
        })
    })

    describe('边界情况', () => {
        it('应该处理空内容', () => {
            const emptyMessage = {
                ...mockAssistantMessage,
                content: '',
            }

            const { container } = render(<ChatMessageComponent message={emptyMessage} />)
            expect(container).toBeInTheDocument()
        })

        it('应该处理特殊字符', () => {
            const messageWithSpecialChars = {
                ...mockAssistantMessage,
                content: 'Test <script>alert("xss")</script> content',
            }

            render(<ChatMessageComponent message={messageWithSpecialChars} />)

            // dangerouslySetInnerHTML 会渲染 HTML，但我们的 Markdown 解析器应该处理它
            expect(screen.getByText(/Test/)).toBeInTheDocument()
        })

        it('应该处理长文本', () => {
            const longContent = 'A'.repeat(10000)
            const messageWithLongContent = {
                ...mockAssistantMessage,
                content: longContent,
            }

            const { container } = render(<ChatMessageComponent message={messageWithLongContent} />)
            expect(container).toBeInTheDocument()
        })
    })
})
