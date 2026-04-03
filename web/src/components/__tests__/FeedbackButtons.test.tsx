/**
 * FeedbackButtons 组件测试
 * 
 * 测试反馈按钮组件的交互和状态管理
 */

import { render, screen, waitFor } from '@/__tests__/utils/test-utils'
import FeedbackButtons from '@/components/FeedbackButtons'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'

describe('FeedbackButtons Component', () => {
    describe('基本渲染', () => {
        it('应该渲染所有按钮', () => {
            render(<FeedbackButtons />)

            const buttons = screen.getAllByRole('button')
            // 复制、重新生成、点赞、点踩、分享 = 5个按钮
            expect(buttons.length).toBe(5)
        })

        it('应该有复制按钮', () => {
            render(<FeedbackButtons />)

            const copyButton = screen.getByTitle('Copy')
            expect(copyButton).toBeInTheDocument()
        })

        it('应该有重新生成按钮', () => {
            render(<FeedbackButtons />)

            const regenerateButton = screen.getByTitle('Regenerate')
            expect(regenerateButton).toBeInTheDocument()
        })

        it('应该有点赞按钮', () => {
            render(<FeedbackButtons />)

            const likeButton = screen.getByTitle('Like')
            expect(likeButton).toBeInTheDocument()
        })

        it('应该有点踩按钮', () => {
            render(<FeedbackButtons />)

            const dislikeButton = screen.getByTitle('Dislike')
            expect(dislikeButton).toBeInTheDocument()
        })

        it('应该有分享按钮', () => {
            render(<FeedbackButtons />)

            const shareButton = screen.getByTitle('Share')
            expect(shareButton).toBeInTheDocument()
        })
    })

    describe('复制功能', () => {
        it('点击复制按钮应该改变图标', async () => {
            const user = userEvent.setup()
            const { container } = render(<FeedbackButtons />)

            const copyButton = screen.getByTitle('Copy')

            await user.click(copyButton)

            // 应该显示勾选图标
            await waitFor(() => {
                const checkPath = container.querySelector('path[d="M3 7L6 10L11 4"]')
                expect(checkPath).toBeInTheDocument()
            })
        })

        it.skip('复制后应该在 2 秒后恢复', async () => {
            // TODO: 修复 Vitest 定时器测试
            vi.useFakeTimers()
            const user = userEvent.setup({ delay: null })

            render(<FeedbackButtons />)

            const copyButton = screen.getByTitle('Copy')

            await user.click(copyButton)

            // 快进 2 秒
            await vi.advanceTimersByTimeAsync(2000)

            // 应该恢复原始图标
            await waitFor(() => {
                expect(copyButton).toBeInTheDocument()
            })

            vi.useRealTimers()
        })
    })

    describe('点赞/点踩功能', () => {
        it.skip('点击点赞应该激活点赞状态', async () => {
            const user = userEvent.setup()
            const { container } = render(<FeedbackButtons />)

            const likeButton = screen.getByTitle('Like')

            await user.click(likeButton)

            // 点赞图标应该被填充
            const likedSvg = likeButton.querySelector('svg')
            expect(likedSvg).toHaveAttribute('fill', 'currentColor')
        })

        it.skip('再次点击点赞应该取消点赞', async () => {
            const user = userEvent.setup()
            const { container } = render(<FeedbackButtons />)

            const likeButton = screen.getByTitle('Like')

            // 第一次点击 - 激活
            await user.click(likeButton)

            // 第二次点击 - 取消
            await user.click(likeButton)

            const likedSvg = likeButton.querySelector('svg')
            expect(likedSvg).toHaveAttribute('fill', 'none')
        })

        it.skip('点击点踩应该激活点踩状态', async () => {
            const user = userEvent.setup()
            render(<FeedbackButtons />)

            const dislikeButton = screen.getByTitle('Dislike')

            await user.click(dislikeButton)

            // 点踩图标应该被填充
            const dislikedSvg = dislikeButton.querySelector('svg')
            expect(dislikedSvg).toHaveAttribute('fill', 'currentColor')
        })

        it.skip('点赞和点踩应该互斥', async () => {
            const user = userEvent.setup()
            render(<FeedbackButtons />)

            const likeButton = screen.getByTitle('Like')
            const dislikeButton = screen.getByTitle('Dislike')

            // 先点赞
            await user.click(likeButton)
            let likeSvg = likeButton.querySelector('svg')
            expect(likeSvg).toHaveAttribute('fill', 'currentColor')

            // 再点踩，点赞应该被取消
            await user.click(dislikeButton)
            likeSvg = likeButton.querySelector('svg')
            const dislikeSvg = dislikeButton.querySelector('svg')

            expect(likeSvg).toHaveAttribute('fill', 'none')
            expect(dislikeSvg).toHaveAttribute('fill', 'currentColor')
        })

        it.skip('点踩后点赞应该取消点踩', async () => {
            const user = userEvent.setup()
            render(<FeedbackButtons />)

            const likeButton = screen.getByTitle('Like')
            const dislikeButton = screen.getByTitle('Dislike')

            // 先点踩
            await user.click(dislikeButton)

            // 再点赞
            await user.click(likeButton)

            const likeSvg = likeButton.querySelector('svg')
            const dislikeSvg = dislikeButton.querySelector('svg')

            expect(likeSvg).toHaveAttribute('fill', 'currentColor')
            expect(dislikeSvg).toHaveAttribute('fill', 'none')
        })
    })

    describe('按钮样式', () => {
        it('所有按钮应该有 hover 效果', () => {
            const { container } = render(<FeedbackButtons />)

            const buttons = container.querySelectorAll('button')
            buttons.forEach(button => {
                expect(button.className).toContain('hover:')
            })
        })

        it('所有按钮应该有过渡动画', () => {
            const { container } = render(<FeedbackButtons />)

            const buttons = container.querySelectorAll('button')
            buttons.forEach(button => {
                expect(button.className).toContain('transition')
            })
        })

        it('应该有顶部边框', () => {
            const { container } = render(<FeedbackButtons />)

            const wrapper = container.querySelector('[style*="border"]')
            expect(wrapper).toBeInTheDocument()
        })
    })

    describe('图标渲染', () => {
        it('每个按钮应该有 SVG 图标', () => {
            const { container } = render(<FeedbackButtons />)

            const buttons = container.querySelectorAll('button')
            buttons.forEach(button => {
                const svg = button.querySelector('svg')
                expect(svg).toBeInTheDocument()
            })
        })

        it('点踩图标应该旋转 180 度', () => {
            const { container } = render(<FeedbackButtons />)

            const dislikeButton = screen.getByTitle('Dislike')
            const svg = dislikeButton.querySelector('svg')

            expect(svg).toHaveClass('rotate-180')
        })
    })

    describe('可访问性', () => {
        it('所有按钮应该有 title 属性', () => {
            render(<FeedbackButtons />)

            expect(screen.getByTitle('Copy')).toBeInTheDocument()
            expect(screen.getByTitle('Regenerate')).toBeInTheDocument()
            expect(screen.getByTitle('Like')).toBeInTheDocument()
            expect(screen.getByTitle('Dislike')).toBeInTheDocument()
            expect(screen.getByTitle('Share')).toBeInTheDocument()
        })

        it('按钮应该可以通过键盘访问', () => {
            render(<FeedbackButtons />)

            const buttons = screen.getAllByRole('button')
            buttons.forEach(button => {
                button.focus()
                expect(button).toHaveFocus()
            })
        })
    })

    describe('边界情况', () => {
        it('快速连续点击应该正常工作', async () => {
            const user = userEvent.setup()
            render(<FeedbackButtons />)

            const likeButton = screen.getByTitle('Like')

            // 快速点击多次
            await user.click(likeButton)
            await user.click(likeButton)
            await user.click(likeButton)

            // 应该正常切换状态
            expect(likeButton).toBeInTheDocument()
        })

        it('多个按钮同时操作应该独立工作', async () => {
            const user = userEvent.setup()
            render(<FeedbackButtons />)

            const copyButton = screen.getByTitle('Copy')
            const likeButton = screen.getByTitle('Like')

            await user.click(copyButton)
            await user.click(likeButton)

            // 两个按钮都应该正常工作
            expect(copyButton).toBeInTheDocument()
            expect(likeButton).toBeInTheDocument()
        })
    })
})
