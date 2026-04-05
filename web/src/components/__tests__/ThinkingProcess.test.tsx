/**
 * ThinkingProcess 组件测试
 *
 * 测试 Agent 执行过程展示组件
 */

import { render, screen, fireEvent } from '@/__tests__/utils/test-utils'
import ThinkingProcess from '@/components/ThinkingProcess'
import { mockAgentSteps } from '@/__tests__/mocks/data'
import { AgentStep } from '@/lib/types'
import { describe, it, expect } from 'vitest'

describe('ThinkingProcess Component', () => {
    describe('基本渲染', () => {
        it('应该渲染 Thinking process 标题', () => {
            render(<ThinkingProcess steps={mockAgentSteps} />)

            expect(screen.getByText('Thinking process')).toBeInTheDocument()
        })

        it('默认应该是折叠状态', () => {
            const { container } = render(<ThinkingProcess steps={mockAgentSteps} />)

            // 步骤详情不应该显示
            expect(screen.queryByText('Step 1:')).not.toBeInTheDocument()
        })

        it('defaultExpanded=true 时应该展开', () => {
            render(<ThinkingProcess steps={mockAgentSteps} defaultExpanded={true} />)

            // 步骤详情应该显示
            expect(screen.getByText('Step 1:')).toBeInTheDocument()
        })
    })

    describe('展开/折叠交互', () => {
        it('点击标题应该切换展开状态', () => {
            render(<ThinkingProcess steps={mockAgentSteps} />)

            const button = screen.getByRole('button', { name: /Thinking process/i })

            // 初始折叠
            expect(screen.queryByText('Step 1:')).not.toBeInTheDocument()

            // 点击展开
            fireEvent.click(button)
            expect(screen.getByText('Step 1:')).toBeInTheDocument()

            // 再次点击折叠
            fireEvent.click(button)
            expect(screen.queryByText('Step 1:')).not.toBeInTheDocument()
        })

        it('展开时箭头应该旋转', () => {
            const { container } = render(<ThinkingProcess steps={mockAgentSteps} />)

            const button = screen.getByRole('button', { name: /Thinking process/i })
            const svg = container.querySelector('svg')

            // 初始状态
            expect(svg).not.toHaveClass('rotate-180')

            // 点击展开
            fireEvent.click(button)
            expect(svg).toHaveClass('rotate-180')
        })
    })

    describe('步骤状态显示', () => {
        it('应该显示所有步骤', () => {
            render(<ThinkingProcess steps={mockAgentSteps} defaultExpanded={true} />)

            expect(screen.getByText('Step 1:')).toBeInTheDocument()
            expect(screen.getByText('Step 2:')).toBeInTheDocument()
            expect(screen.getByText('Step 3:')).toBeInTheDocument()
        })

        it('应该显示 Agent 名称', () => {
            render(<ThinkingProcess steps={mockAgentSteps} defaultExpanded={true} />)

            expect(screen.getByText('Log Analytics Agent')).toBeInTheDocument()
            expect(screen.getByText('Jira Knowledge Agent')).toBeInTheDocument()
            expect(screen.getByText('Orchestrator')).toBeInTheDocument()
        })

        it('应该显示状态文本', () => {
            render(<ThinkingProcess steps={mockAgentSteps} defaultExpanded={true} />)

            expect(screen.getByText('Analyzing FOTA logs...')).toBeInTheDocument()
            expect(screen.getByText('Searching Jira tickets...')).toBeInTheDocument()
            expect(screen.getByText('Waiting...')).toBeInTheDocument()
        })

        it('应该显示完成步骤的结果', () => {
            render(<ThinkingProcess steps={mockAgentSteps} defaultExpanded={true} />)

            expect(screen.getByText('Found 3 relevant log entries')).toBeInTheDocument()
        })
    })

    describe('状态图标', () => {
        it('completed 状态应该显示勾选图标', () => {
            const completedStep: AgentStep[] = [{
                stepNumber: 1,
                agentName: 'Test Agent',
                status: 'completed',
                statusText: 'Done',
                result: 'Success',
            }]

            const { container } = render(
                <ThinkingProcess steps={completedStep} defaultExpanded={true} />
            )

            // 检查是否有绿色背景的圆形（completed 图标）
            // 查找包含勾选标记的 SVG
            const checkmark = container.querySelector('svg path[d="M2 5L4 7L8 3"]')
            expect(checkmark).toBeInTheDocument()
        })

        it('running 状态应该显示旋转动画', () => {
            const runningStep: AgentStep[] = [{
                stepNumber: 1,
                agentName: 'Test Agent',
                status: 'running',
                statusText: 'Processing...',
            }]

            const { container } = render(
                <ThinkingProcess steps={runningStep} defaultExpanded={true} />
            )

            // 检查是否有旋转动画类
            const spinner = container.querySelector('.animate-spin')
            expect(spinner).toBeInTheDocument()
        })

        it('pending 状态应该显示灰色圆圈', () => {
            const pendingStep: AgentStep[] = [{
                stepNumber: 1,
                agentName: 'Test Agent',
                status: 'pending',
                statusText: 'Waiting...',
            }]

            const { container } = render(
                <ThinkingProcess steps={pendingStep} defaultExpanded={true} />
            )

            // pending 状态的圆圈应该存在
            const circles = container.querySelectorAll('.w-4.h-4.rounded-full')
            expect(circles.length).toBeGreaterThan(0)
        })
    })

    describe('当前步骤显示', () => {
        it('有运行中的步骤时应该显示当前 Agent', () => {
            render(<ThinkingProcess steps={mockAgentSteps} />)

            // mockAgentSteps 中第二个步骤是 running 状态
            expect(screen.getByText('— Jira Knowledge Agent')).toBeInTheDocument()
        })

        it('所有步骤完成时应该显示 Completed', () => {
            const allCompleted: AgentStep[] = [
                {
                    stepNumber: 1,
                    agentName: 'Agent 1',
                    status: 'completed',
                    statusText: 'Done',
                },
                {
                    stepNumber: 2,
                    agentName: 'Agent 2',
                    status: 'completed',
                    statusText: 'Done',
                },
            ]

            render(<ThinkingProcess steps={allCompleted} />)

            expect(screen.getByText('— Completed')).toBeInTheDocument()
        })
    })

    describe('连接线渲染', () => {
        it('非最后一个步骤应该显示连接线', () => {
            const { container } = render(
                <ThinkingProcess steps={mockAgentSteps} defaultExpanded={true} />
            )

            // 查找连接线元素（垂直线）
            const connectors = container.querySelectorAll('.w-0\\.5')
            // 应该有 2 条连接线（3 个步骤，最后一个没有连接线）
            expect(connectors.length).toBeGreaterThan(0)
        })
    })

    describe('边界情况', () => {
        it('应该处理空步骤数组', () => {
            const { container } = render(<ThinkingProcess steps={[]} />)

            expect(screen.getByText('Thinking process')).toBeInTheDocument()
            expect(container).toBeInTheDocument()
        })

        it('应该处理单个步骤', () => {
            const singleStep: AgentStep[] = [{
                stepNumber: 1,
                agentName: 'Single Agent',
                status: 'completed',
                statusText: 'Done',
            }]

            render(<ThinkingProcess steps={singleStep} defaultExpanded={true} />)

            expect(screen.getByText('Single Agent')).toBeInTheDocument()
        })

        it('应该处理没有结果的步骤', () => {
            const stepWithoutResult: AgentStep[] = [{
                stepNumber: 1,
                agentName: 'Test Agent',
                status: 'running',
                statusText: 'Processing...',
                // 没有 result 字段
            }]

            render(<ThinkingProcess steps={stepWithoutResult} defaultExpanded={true} />)

            expect(screen.getByText('Test Agent')).toBeInTheDocument()
            expect(screen.getByText('Processing...')).toBeInTheDocument()
        })
    })

    describe('动画效果', () => {
        it('展开时应该有滑动动画', () => {
            const { container } = render(<ThinkingProcess steps={mockAgentSteps} />)

            const button = screen.getByRole('button', { name: /Thinking process/i })
            fireEvent.click(button)

            // 检查动画类
            const animatedDiv = container.querySelector('.animate-slide-down')
            expect(animatedDiv).toBeInTheDocument()
        })
    })
})
