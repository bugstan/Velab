import { render, screen } from '@/__tests__/utils/test-utils'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import SessionSidebar from '@/components/SessionSidebar'
import { ChatSession } from '@/lib/types'

const buildSession = (id: string, title: string): ChatSession => ({
    id,
    title,
    messages: [],
    createdAt: new Date('2026-01-01T00:00:00.000Z'),
    updatedAt: new Date('2026-01-01T00:00:00.000Z'),
    titleSource: 'manual',
    titleAutoOptimized: false,
    turnCount: 0,
})

describe('SessionSidebar', () => {
    it('点击菜单删除不应触发选中回调', async () => {
        const user = userEvent.setup()
        const onSelectSession = vi.fn()
        const onDeleteSession = vi.fn()
        const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

        render(
            <SessionSidebar
                sessions={[buildSession('session-1', '会话一')]}
                activeSessionId="session-1"
                onSelectSession={onSelectSession}
                onCreateSession={() => { }}
                onDeleteSession={onDeleteSession}
            />
        )

        await user.click(screen.getByLabelText('会话操作'))
        await user.click(screen.getByText('删除'))

        expect(onDeleteSession).toHaveBeenCalledWith('session-1')
        expect(onDeleteSession).toHaveBeenCalledTimes(1)
        expect(onSelectSession).not.toHaveBeenCalled()
        confirmSpy.mockRestore()
    })
})
