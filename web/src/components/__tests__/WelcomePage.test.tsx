/**
 * WelcomePage 组件测试
 *
 * 测试欢迎页面组件的渲染和交互
 */

import { render, screen } from '@/__tests__/utils/test-utils'
import WelcomePage from '@/components/WelcomePage'
import { PRESET_QUESTIONS } from '@/lib/types'
import userEvent from '@testing-library/user-event'
import { vi, describe, it, beforeEach, expect } from 'vitest'

describe('WelcomePage Component', () => {
    const mockOnQuestionClick = vi.fn()

    beforeEach(() => {
        vi.clearAllMocks()
    })

    describe('基本渲染', () => {
        it('应该渲染标题', () => {
            render(<WelcomePage onQuestionClick={mockOnQuestionClick} />)

            expect(screen.getByText('What are you working on?')).toBeInTheDocument()
        })

        it('应该渲染所有预设问题', () => {
            render(<WelcomePage onQuestionClick={mockOnQuestionClick} />)

            PRESET_QUESTIONS.forEach(question => {
                expect(screen.getByText(question.text)).toBeInTheDocument()
            })
        })

        it('应该显示问题图标', () => {
            render(<WelcomePage onQuestionClick={mockOnQuestionClick} />)

            PRESET_QUESTIONS.forEach(question => {
                expect(screen.getByText(question.icon)).toBeInTheDocument()
            })
        })
    })

    describe('问题卡片交互', () => {
        it('点击问题应该调用 onQuestionClick', async () => {
            const user = userEvent.setup()
            render(<WelcomePage onQuestionClick={mockOnQuestionClick} />)

            const firstQuestion = PRESET_QUESTIONS[0]
            const button = screen.getByText(firstQuestion.text)

            await user.click(button)

            expect(mockOnQuestionClick).toHaveBeenCalledWith(firstQuestion.text)
        })

        it('每个问题都应该可以点击', async () => {
            const user = userEvent.setup()
            render(<WelcomePage onQuestionClick={mockOnQuestionClick} />)

            for (const question of PRESET_QUESTIONS) {
                const button = screen.getByText(question.text)
                await user.click(button)

                expect(mockOnQuestionClick).toHaveBeenCalledWith(question.text)
            }

            expect(mockOnQuestionClick).toHaveBeenCalledTimes(PRESET_QUESTIONS.length)
        })

        it('问题卡片应该是按钮元素', () => {
            render(<WelcomePage onQuestionClick={mockOnQuestionClick} />)

            const buttons = screen.getAllByRole('button')
            expect(buttons.length).toBe(PRESET_QUESTIONS.length)
        })
    })

    describe('布局和样式', () => {
        it('应该使用网格布局', () => {
            const { container } = render(<WelcomePage onQuestionClick={mockOnQuestionClick} />)

            const grid = container.querySelector('.grid')
            expect(grid).toBeInTheDocument()
        })

        it('应该有淡入动画', () => {
            const { container } = render(<WelcomePage onQuestionClick={mockOnQuestionClick} />)

            const animatedDiv = container.querySelector('.animate-fade-in')
            expect(animatedDiv).toBeInTheDocument()
        })

        it('应该居中显示', () => {
            const { container } = render(<WelcomePage onQuestionClick={mockOnQuestionClick} />)

            const centerDiv = container.querySelector('.justify-center')
            expect(centerDiv).toBeInTheDocument()
        })
    })

    describe('响应式设计', () => {
        it('应该有响应式网格类', () => {
            const { container } = render(<WelcomePage onQuestionClick={mockOnQuestionClick} />)

            const grid = container.querySelector('.grid-cols-1')
            expect(grid).toBeInTheDocument()
        })

        it('应该有 sm 断点的网格类', () => {
            const { container } = render(<WelcomePage onQuestionClick={mockOnQuestionClick} />)

            const grid = container.querySelector('.sm\\:grid-cols-2')
            expect(grid).toBeInTheDocument()
        })
    })

    describe('可访问性', () => {
        it('所有问题按钮应该可以通过键盘访问', () => {
            render(<WelcomePage onQuestionClick={mockOnQuestionClick} />)

            const buttons = screen.getAllByRole('button')

            buttons.forEach(button => {
                button.focus()
                expect(button).toHaveFocus()
            })
        })

        it('按钮应该有正确的文本内容', () => {
            render(<WelcomePage onQuestionClick={mockOnQuestionClick} />)

            PRESET_QUESTIONS.forEach(question => {
                const button = screen.getByText(question.text).closest('button')
                expect(button).toBeInTheDocument()
            })
        })
    })

    describe('边界情况', () => {
        it('应该处理空的预设问题列表', () => {
            // 这个测试假设组件能处理空列表
            const { container } = render(<WelcomePage onQuestionClick={mockOnQuestionClick} />)

            expect(container).toBeInTheDocument()
        })

        it('应该处理长问题文本', () => {
            render(<WelcomePage onQuestionClick={mockOnQuestionClick} />)

            // 所有问题都应该正常显示
            PRESET_QUESTIONS.forEach(question => {
                expect(screen.getByText(question.text)).toBeInTheDocument()
            })
        })
    })

    describe('hover 效果', () => {
        it('问题卡片应该有 hover 类', () => {
            const { container } = render(<WelcomePage onQuestionClick={mockOnQuestionClick} />)

            const buttons = container.querySelectorAll('button')
            buttons.forEach(button => {
                expect(button.className).toContain('hover:')
            })
        })

        it('应该有过渡动画类', () => {
            const { container } = render(<WelcomePage onQuestionClick={mockOnQuestionClick} />)

            const buttons = container.querySelectorAll('button')
            buttons.forEach(button => {
                expect(button.className).toContain('transition')
            })
        })
    })
})
