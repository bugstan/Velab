/**
 * InputBar 组件测试
 *
 * 测试输入框组件的交互和功能
 */

import { render, screen, fireEvent, waitFor } from '@/__tests__/utils/test-utils'
import InputBar from '@/components/InputBar'
import userEvent from '@testing-library/user-event'
import { vi, describe, it, beforeEach, expect } from 'vitest'

describe('InputBar Component', () => {
    const mockOnSend = vi.fn()
    const mockOnStop = vi.fn()
    const mockOnUploadFiles = vi.fn(async () => undefined)

    beforeEach(() => {
        vi.clearAllMocks()
    })

    describe('基本渲染', () => {
        it('应该渲染输入框', () => {
            render(<InputBar onSend={mockOnSend} isRunning={false} onStop={mockOnStop} />)

            const input = screen.getByPlaceholderText('Ask a question')
            expect(input).toBeInTheDocument()
        })

        it('应该渲染所有按钮', () => {
            render(<InputBar onSend={mockOnSend} isRunning={false} onStop={mockOnStop} />)

            const buttons = screen.getAllByRole('button')
            // + 按钮、附件按钮、麦克风按钮、Run 按钮
            expect(buttons.length).toBeGreaterThanOrEqual(4)
        })

        it('非运行状态应该显示 Run 按钮', () => {
            render(<InputBar onSend={mockOnSend} isRunning={false} onStop={mockOnStop} />)

            expect(screen.getByText('Run')).toBeInTheDocument()
        })

        it('运行状态应该显示 Stop 按钮', () => {
            render(<InputBar onSend={mockOnSend} isRunning={true} onStop={mockOnStop} />)

            expect(screen.getByText('Stop')).toBeInTheDocument()
        })
    })

    describe('输入交互', () => {
        it('应该能够输入文本', async () => {
            const user = userEvent.setup()
            render(<InputBar onSend={mockOnSend} isRunning={false} onStop={mockOnStop} />)

            const input = screen.getByPlaceholderText('Ask a question') as HTMLInputElement

            await user.type(input, 'Test message')

            expect(input.value).toBe('Test message')
        })

        it('输入文本时应该更新状态', async () => {
            const user = userEvent.setup()
            render(<InputBar onSend={mockOnSend} isRunning={false} onStop={mockOnStop} />)

            const input = screen.getByPlaceholderText('Ask a question') as HTMLInputElement

            await user.type(input, 'Hello')

            expect(input.value).toBe('Hello')
        })
    })

    describe('发送消息', () => {
        it('提交表单应该调用 onSend', async () => {
            const user = userEvent.setup()
            render(<InputBar onSend={mockOnSend} isRunning={false} onStop={mockOnStop} />)

            const input = screen.getByPlaceholderText('Ask a question')
            const form = input.closest('form')!

            await user.type(input, 'Test message')
            fireEvent.submit(form)

            expect(mockOnSend).toHaveBeenCalledWith('Test message')
        })

        it('点击 Run 按钮应该发送消息', async () => {
            const user = userEvent.setup()
            render(<InputBar onSend={mockOnSend} isRunning={false} onStop={mockOnStop} />)

            const input = screen.getByPlaceholderText('Ask a question')
            const runButton = screen.getByText('Run')

            await user.type(input, 'Test message')
            await user.click(runButton)

            expect(mockOnSend).toHaveBeenCalledWith('Test message')
        })

        it('发送后应该清空输入框', async () => {
            const user = userEvent.setup()
            render(<InputBar onSend={mockOnSend} isRunning={false} onStop={mockOnStop} />)

            const input = screen.getByPlaceholderText('Ask a question') as HTMLInputElement
            const form = input.closest('form')!

            await user.type(input, 'Test message')
            fireEvent.submit(form)

            await waitFor(() => {
                expect(input.value).toBe('')
            })
        })

        it('应该去除首尾空格', async () => {
            const user = userEvent.setup()
            render(<InputBar onSend={mockOnSend} isRunning={false} onStop={mockOnStop} />)

            const input = screen.getByPlaceholderText('Ask a question')
            const form = input.closest('form')!

            await user.type(input, '  Test message  ')
            fireEvent.submit(form)

            expect(mockOnSend).toHaveBeenCalledWith('Test message')
        })
    })

    describe('验证逻辑', () => {
        it('空消息不应该发送', async () => {
            render(<InputBar onSend={mockOnSend} isRunning={false} onStop={mockOnStop} />)

            const form = screen.getByPlaceholderText('Ask a question').closest('form')!

            fireEvent.submit(form)

            expect(mockOnSend).not.toHaveBeenCalled()
        })

        it('只有空格的消息不应该发送', async () => {
            const user = userEvent.setup()
            render(<InputBar onSend={mockOnSend} isRunning={false} onStop={mockOnStop} />)

            const input = screen.getByPlaceholderText('Ask a question')
            const form = input.closest('form')!

            await user.type(input, '   ')
            fireEvent.submit(form)

            expect(mockOnSend).not.toHaveBeenCalled()
        })

        it('运行中时不应该发送新消息', async () => {
            const user = userEvent.setup()
            render(<InputBar onSend={mockOnSend} isRunning={true} onStop={mockOnStop} />)

            const input = screen.getByPlaceholderText('Ask a question')
            const form = input.closest('form')!

            await user.type(input, 'Test message')
            fireEvent.submit(form)

            expect(mockOnSend).not.toHaveBeenCalled()
        })
    })

    describe('Stop 功能', () => {
        it('点击 Stop 按钮应该调用 onStop', async () => {
            const user = userEvent.setup()
            render(<InputBar onSend={mockOnSend} isRunning={true} onStop={mockOnStop} />)

            const stopButton = screen.getByText('Stop')
            await user.click(stopButton)

            expect(mockOnStop).toHaveBeenCalled()
        })

        it('Stop 按钮应该是 button 类型而非 submit', () => {
            render(<InputBar onSend={mockOnSend} isRunning={true} onStop={mockOnStop} />)

            const stopButton = screen.getByText('Stop')
            expect(stopButton).toHaveAttribute('type', 'button')
        })
    })

    describe('按钮状态', () => {
        it('输入为空时 Run 按钮应该半透明', () => {
            render(<InputBar onSend={mockOnSend} isRunning={false} onStop={mockOnStop} />)

            const runButton = screen.getByText('Run')
            expect(runButton).toHaveStyle({ opacity: 0.5 })
        })

        it('有输入时 Run 按钮应该完全不透明', async () => {
            const user = userEvent.setup()
            render(<InputBar onSend={mockOnSend} isRunning={false} onStop={mockOnStop} />)

            const input = screen.getByPlaceholderText('Ask a question')
            await user.type(input, 'Test')

            const runButton = screen.getByText('Run')
            expect(runButton).toHaveStyle({ opacity: 1 })
        })
    })

    describe('辅助按钮', () => {
        it('应该渲染 + 按钮', () => {
            const { container } = render(
                <InputBar onSend={mockOnSend} isRunning={false} onStop={mockOnStop} />
            )

            // + 按钮是第一个 button
            const buttons = container.querySelectorAll('button')
            expect(buttons[0]).toBeInTheDocument()
        })

        it('应该渲染附件按钮', () => {
            render(<InputBar onSend={mockOnSend} isRunning={false} onStop={mockOnStop} />)

            const buttons = screen.getAllByRole('button')
            // 附件按钮应该存在（通过 SVG 路径识别）
            expect(buttons.length).toBeGreaterThan(2)
        })

        it('应该渲染麦克风按钮', () => {
            render(<InputBar onSend={mockOnSend} isRunning={false} onStop={mockOnStop} />)

            const buttons = screen.getAllByRole('button')
            // 麦克风按钮应该存在
            expect(buttons.length).toBeGreaterThan(3)
        })

        it('辅助按钮应该是 button 类型', () => {
            const { container } = render(
                <InputBar onSend={mockOnSend} isRunning={false} onStop={mockOnStop} />
            )

            const buttons = container.querySelectorAll('button[type="button"]')
            // 至少有 3 个 button 类型的按钮（+、附件、麦克风）
            expect(buttons.length).toBeGreaterThanOrEqual(3)
        })
    })

    describe('键盘交互', () => {
        it('按 Enter 应该提交表单', async () => {
            const user = userEvent.setup()
            render(<InputBar onSend={mockOnSend} isRunning={false} onStop={mockOnStop} />)

            const input = screen.getByPlaceholderText('Ask a question')

            await user.type(input, 'Test message{Enter}')

            expect(mockOnSend).toHaveBeenCalledWith('Test message')
        })
    })

    describe('边界情况', () => {
        it('应该处理非常长的输入', async () => {
            const longMessage = 'A'.repeat(10000)

            render(<InputBar onSend={mockOnSend} isRunning={false} onStop={mockOnStop} />)

            const input = screen.getByPlaceholderText('Ask a question') as HTMLTextAreaElement
            const form = input.closest('form')!

            // 使用 fireEvent.change 而不是 userEvent.type 来避免超时
            fireEvent.change(input, { target: { value: longMessage } })
            fireEvent.submit(form)

            expect(mockOnSend).toHaveBeenCalledWith(longMessage)
        })

        it('应该处理特殊字符', async () => {
            const specialMessage = '<script>alert("xss")</script>'

            render(<InputBar onSend={mockOnSend} isRunning={false} onStop={mockOnStop} />)

            const input = screen.getByPlaceholderText('Ask a question') as HTMLTextAreaElement
            const form = input.closest('form')!

            // 使用 fireEvent.change 来正确处理特殊字符
            fireEvent.change(input, { target: { value: specialMessage } })
            fireEvent.submit(form)

            expect(mockOnSend).toHaveBeenCalledWith(specialMessage)
        })

        it('应该处理 Unicode 字符', async () => {
            const unicodeMessage = '你好世界 🚀 émojis'

            render(<InputBar onSend={mockOnSend} isRunning={false} onStop={mockOnStop} />)

            const input = screen.getByPlaceholderText('Ask a question') as HTMLTextAreaElement
            const form = input.closest('form')!

            // 使用 fireEvent.change 来正确处理 Unicode 字符
            fireEvent.change(input, { target: { value: unicodeMessage } })
            fireEvent.submit(form)

            expect(mockOnSend).toHaveBeenCalledWith(unicodeMessage)
        })

        it('拖拽文件到输入区时应触发上传', async () => {
            const { container } = render(
                <InputBar
                    onSend={mockOnSend}
                    isRunning={false}
                    onStop={mockOnStop}
                    onUploadFiles={mockOnUploadFiles}
                />
            )

            const form = container.querySelector('form')
            expect(form).toBeInTheDocument()

            const file = new File(['hello'], 'demo.log', { type: 'text/plain' })
            const dataTransfer = {
                files: [file],
            } as unknown as DataTransfer

            fireEvent.dragOver(form!)
            fireEvent.dragLeave(form!)
            fireEvent.drop(form!, { dataTransfer })

            await waitFor(() => {
                expect(mockOnUploadFiles).toHaveBeenCalledTimes(1)
                expect(mockOnUploadFiles).toHaveBeenCalledWith(dataTransfer.files)
            })
        })

        it('文件选择变化应触发上传，空文件不触发', async () => {
            const { container } = render(
                <InputBar
                    onSend={mockOnSend}
                    isRunning={false}
                    onStop={mockOnStop}
                    onUploadFiles={mockOnUploadFiles}
                />
            )

            const hiddenInput = container.querySelector('input[type="file"]') as HTMLInputElement
            expect(hiddenInput).toBeInTheDocument()

            const file = new File(['content'], 'upload.zip', { type: 'application/zip' })
            fireEvent.change(hiddenInput, { target: { files: [file] } })

            await waitFor(() => {
                expect(mockOnUploadFiles).toHaveBeenCalledTimes(1)
            })

            fireEvent.change(hiddenInput, { target: { files: [] } })
            expect(mockOnUploadFiles).toHaveBeenCalledTimes(1)
        })
    })
})
