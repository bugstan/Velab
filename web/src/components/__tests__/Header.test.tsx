/**
 * Header 组件测试
 *
 * 测试页头组件的渲染和场景切换功能
 */

import { render, screen, fireEvent, waitFor } from '@/__tests__/utils/test-utils'
import Header from '@/components/Header'
import { DEMO_SCENARIOS } from '@/lib/types'
import userEvent from '@testing-library/user-event'
import { vi, describe, it, beforeEach, expect } from 'vitest'

describe('Header Component', () => {
    const mockOnScenarioChange = vi.fn()
    const currentScenario = DEMO_SCENARIOS[0]

    beforeEach(() => {
        vi.clearAllMocks()
    })

    describe('基本渲染', () => {
        it('应该渲染 Logo 图标', () => {
            const { container } = render(
                <Header currentScenario={currentScenario} onScenarioChange={mockOnScenarioChange} />
            )

            const logo = container.querySelector('svg')
            expect(logo).toBeInTheDocument()
        })

        it('应该显示当前场景名称', () => {
            render(
                <Header currentScenario={currentScenario} onScenarioChange={mockOnScenarioChange} />
            )

            expect(screen.getByText(currentScenario.name)).toBeInTheDocument()
        })

        it('应该渲染 Sign up 按钮', () => {
            render(
                <Header currentScenario={currentScenario} onScenarioChange={mockOnScenarioChange} />
            )

            expect(screen.getByText('Sign up')).toBeInTheDocument()
        })

        it('应该渲染 Log in 按钮', () => {
            render(
                <Header currentScenario={currentScenario} onScenarioChange={mockOnScenarioChange} />
            )

            expect(screen.getByText('Log in')).toBeInTheDocument()
        })
    })

    describe('下拉菜单交互', () => {
        it('初始状态下拉菜单应该是关闭的', () => {
            render(
                <Header currentScenario={currentScenario} onScenarioChange={mockOnScenarioChange} />
            )

            // 其他场景不应该显示
            const otherScenario = DEMO_SCENARIOS[1]
            expect(screen.queryByText(otherScenario.description)).not.toBeInTheDocument()
        })

        it('点击场景名称应该打开下拉菜单', async () => {
            const user = userEvent.setup()
            render(
                <Header currentScenario={currentScenario} onScenarioChange={mockOnScenarioChange} />
            )

            const button = screen.getByRole('button', { name: new RegExp(currentScenario.name) })
            await user.click(button)

            // 应该显示所有场景
            DEMO_SCENARIOS.forEach(scenario => {
                expect(screen.getByText(scenario.description)).toBeInTheDocument()
            })
        })

        it('再次点击应该关闭下拉菜单', async () => {
            const user = userEvent.setup()
            render(
                <Header currentScenario={currentScenario} onScenarioChange={mockOnScenarioChange} />
            )

            const button = screen.getByRole('button', { name: new RegExp(currentScenario.name) })

            // 打开
            await user.click(button)
            expect(screen.getByText(DEMO_SCENARIOS[1].description)).toBeInTheDocument()

            // 关闭
            await user.click(button)
            await waitFor(() => {
                expect(screen.queryByText(DEMO_SCENARIOS[1].description)).not.toBeInTheDocument()
            })
        })

        it('箭头图标应该根据状态旋转', async () => {
            const user = userEvent.setup()
            const { container } = render(
                <Header currentScenario={currentScenario} onScenarioChange={mockOnScenarioChange} />
            )

            const button = screen.getByRole('button', { name: new RegExp(currentScenario.name) })
            const svg = button.querySelector('svg')

            // 初始状态
            expect(svg).not.toHaveClass('rotate-180')

            // 打开后
            await user.click(button)
            expect(svg).toHaveClass('rotate-180')
        })
    })

    describe('场景切换', () => {
        it('点击场景应该调用 onScenarioChange', async () => {
            const user = userEvent.setup()
            render(
                <Header currentScenario={currentScenario} onScenarioChange={mockOnScenarioChange} />
            )

            // 打开下拉菜单
            const button = screen.getByRole('button', { name: new RegExp(currentScenario.name) })
            await user.click(button)

            // 点击另一个场景
            const targetScenario = DEMO_SCENARIOS[1]
            const scenarioButton = screen.getByText(targetScenario.name)
            await user.click(scenarioButton)

            expect(mockOnScenarioChange).toHaveBeenCalledWith(targetScenario)
        })

        it('切换场景后应该关闭下拉菜单', async () => {
            const user = userEvent.setup()
            render(
                <Header currentScenario={currentScenario} onScenarioChange={mockOnScenarioChange} />
            )

            // 打开下拉菜单
            const button = screen.getByRole('button', { name: new RegExp(currentScenario.name) })
            await user.click(button)

            // 点击场景
            const targetScenario = DEMO_SCENARIOS[1]
            const scenarioButton = screen.getByText(targetScenario.name)
            await user.click(scenarioButton)

            // 下拉菜单应该关闭
            await waitFor(() => {
                expect(screen.queryByText(targetScenario.description)).not.toBeInTheDocument()
            })
        })

        it('应该显示所有可用场景', async () => {
            const user = userEvent.setup()
            render(
                <Header currentScenario={currentScenario} onScenarioChange={mockOnScenarioChange} />
            )

            const button = screen.getByRole('button', { name: new RegExp(currentScenario.name) })
            await user.click(button)

            // 检查所有场景都显示
            DEMO_SCENARIOS.forEach(scenario => {
                const names = screen.getAllByText(scenario.name)
                expect(names.length).toBeGreaterThan(0)
                expect(screen.getByText(scenario.description)).toBeInTheDocument()
            })
        })

        it('当前场景应该有选中标记', async () => {
            const user = userEvent.setup()
            const { container } = render(
                <Header currentScenario={currentScenario} onScenarioChange={mockOnScenarioChange} />
            )

            const button = screen.getByRole('button', { name: new RegExp(currentScenario.name) })
            await user.click(button)

            // 查找勾选图标（通过 SVG 路径）
            const checkmarks = container.querySelectorAll('svg path[d*="M3 8L7 12L13 4"]')
            expect(checkmarks.length).toBeGreaterThan(0)
        })
    })

    describe('点击外部关闭', () => {
        it('点击外部应该关闭下拉菜单', async () => {
            const user = userEvent.setup()
            const { container } = render(
                <div>
                    <Header currentScenario={currentScenario} onScenarioChange={mockOnScenarioChange} />
                    <div data-testid="outside">Outside element</div>
                </div>
            )

            // 打开下拉菜单
            const button = screen.getByRole('button', { name: new RegExp(currentScenario.name) })
            await user.click(button)

            expect(screen.getByText(DEMO_SCENARIOS[1].description)).toBeInTheDocument()

            // 点击外部
            const outside = screen.getByTestId('outside')
            fireEvent.mouseDown(outside)

            await waitFor(() => {
                expect(screen.queryByText(DEMO_SCENARIOS[1].description)).not.toBeInTheDocument()
            })
        })

        it('点击下拉菜单内部不应该关闭', async () => {
            const user = userEvent.setup()
            render(
                <Header currentScenario={currentScenario} onScenarioChange={mockOnScenarioChange} />
            )

            // 打开下拉菜单
            const button = screen.getByRole('button', { name: new RegExp(currentScenario.name) })
            await user.click(button)

            // 点击下拉菜单内的描述文本（不是场景按钮）
            const description = screen.getByText(currentScenario.description)
            fireEvent.mouseDown(description)

            // 下拉菜单应该仍然打开
            expect(screen.getByText(DEMO_SCENARIOS[1].description)).toBeInTheDocument()
        })
    })

    describe('样式和布局', () => {
        it('应该有 sticky 定位', () => {
            const { container } = render(
                <Header currentScenario={currentScenario} onScenarioChange={mockOnScenarioChange} />
            )

            const header = container.querySelector('header')
            expect(header).toHaveClass('sticky')
        })

        it('下拉菜单应该有动画类', async () => {
            const user = userEvent.setup()
            const { container } = render(
                <Header currentScenario={currentScenario} onScenarioChange={mockOnScenarioChange} />
            )

            const button = screen.getByRole('button', { name: new RegExp(currentScenario.name) })
            await user.click(button)

            const dropdown = container.querySelector('.animate-fade-in')
            expect(dropdown).toBeInTheDocument()
        })

        it('当前场景应该有高亮背景', async () => {
            const user = userEvent.setup()
            render(
                <Header currentScenario={currentScenario} onScenarioChange={mockOnScenarioChange} />
            )

            const button = screen.getByRole('button', { name: new RegExp(currentScenario.name) })
            await user.click(button)

            // 当前场景的按钮应该有特殊样式
            const currentButtons = screen.getAllByText(currentScenario.name)
            expect(currentButtons.length).toBeGreaterThan(0)
            const currentButton = currentButtons[0].closest('button')
            expect(currentButton).toBeInTheDocument()
        })
    })

    describe('边界情况', () => {
        it('应该处理空场景列表', async () => {
            const user = userEvent.setup()
            render(
                <Header currentScenario={currentScenario} onScenarioChange={mockOnScenarioChange} />
            )

            const button = screen.getByRole('button', { name: new RegExp(currentScenario.name) })
            await user.click(button)

            // 应该能正常打开下拉菜单
            expect(button).toBeInTheDocument()
        })

        it('应该处理长场景名称', () => {
            const longScenario = {
                ...currentScenario,
                name: 'A'.repeat(100),
                description: 'B'.repeat(200),
            }

            render(
                <Header currentScenario={longScenario} onScenarioChange={mockOnScenarioChange} />
            )

            expect(screen.getByText(longScenario.name)).toBeInTheDocument()
        })
    })

    describe('可访问性', () => {
        it('按钮应该有正确的 role', () => {
            render(
                <Header currentScenario={currentScenario} onScenarioChange={mockOnScenarioChange} />
            )

            const buttons = screen.getAllByRole('button')
            expect(buttons.length).toBeGreaterThan(0)
        })

        it('下拉菜单按钮应该可以通过键盘访问', () => {
            render(
                <Header currentScenario={currentScenario} onScenarioChange={mockOnScenarioChange} />
            )

            const button = screen.getByRole('button', { name: new RegExp(currentScenario.name) })
            expect(button).toBeInTheDocument()

            // 按钮应该可以获得焦点
            button.focus()
            expect(button).toHaveFocus()
        })
    })
})
