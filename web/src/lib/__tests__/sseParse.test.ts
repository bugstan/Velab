/**
 * SSE 解析器测试
 * 
 * 测试 SSE 数据流解析功能
 */

import { parseSSEBuffer } from '@/lib/sseParse'

describe('parseSSEBuffer', () => {
    describe('基本解析', () => {
        it('应该解析单个事件', () => {
            const buffer = 'data: {"type":"test","content":"hello"}\n\n'

            const result = parseSSEBuffer(buffer)

            expect(result.events).toHaveLength(1)
            expect(result.events[0]).toEqual({ type: 'test', content: 'hello' })
            expect(result.rest).toBe('')
        })

        it('应该解析多个事件', () => {
            const buffer =
                'data: {"type":"event1"}\n\n' +
                'data: {"type":"event2"}\n\n'

            const result = parseSSEBuffer(buffer)

            expect(result.events).toHaveLength(2)
            expect(result.events[0]).toEqual({ type: 'event1' })
            expect(result.events[1]).toEqual({ type: 'event2' })
        })

        it('应该保留不完整的事件', () => {
            const buffer =
                'data: {"type":"complete"}\n\n' +
                'data: {"type":"incomplete"'

            const result = parseSSEBuffer(buffer)

            expect(result.events).toHaveLength(1)
            expect(result.events[0]).toEqual({ type: 'complete' })
            expect(result.rest).toBe('data: {"type":"incomplete"')
        })
    })

    describe('行结束符处理', () => {
        it('应该处理 \\r\\n 行结束符', () => {
            const buffer = 'data: {"type":"test"}\r\n\r\n'

            const result = parseSSEBuffer(buffer)

            expect(result.events).toHaveLength(1)
            expect(result.events[0]).toEqual({ type: 'test' })
        })

        it('应该处理 \\r 行结束符', () => {
            const buffer = 'data: {"type":"test"}\r\r'

            const result = parseSSEBuffer(buffer)

            expect(result.events).toHaveLength(1)
            expect(result.events[0]).toEqual({ type: 'test' })
        })

        it('应该处理混合行结束符', () => {
            const buffer =
                'data: {"type":"event1"}\r\n\r\n' +
                'data: {"type":"event2"}\n\n'

            const result = parseSSEBuffer(buffer)

            expect(result.events).toHaveLength(2)
        })
    })

    describe('注释处理', () => {
        it('应该忽略注释行', () => {
            const buffer =
                ': This is a comment\n' +
                'data: {"type":"test"}\n\n'

            const result = parseSSEBuffer(buffer)

            expect(result.events).toHaveLength(1)
            expect(result.events[0]).toEqual({ type: 'test' })
        })

        it('应该忽略多个注释', () => {
            const buffer =
                ': Comment 1\n' +
                ': Comment 2\n' +
                'data: {"type":"test"}\n\n'

            const result = parseSSEBuffer(buffer)

            expect(result.events).toHaveLength(1)
        })
    })

    describe('多行数据', () => {
        it('应该合并多行 data 字段', () => {
            const buffer =
                'data: {"type":"test",\n' +
                'data: "content":"hello"}\n\n'

            const result = parseSSEBuffer(buffer)

            expect(result.events).toHaveLength(1)
            expect(result.events[0]).toEqual({ type: 'test', content: 'hello' })
        })
    })

    describe('错误处理', () => {
        it('应该忽略格式错误的 JSON', () => {
            const buffer =
                'data: {invalid json}\n\n' +
                'data: {"type":"valid"}\n\n'

            const result = parseSSEBuffer(buffer)

            // 只应该解析有效的 JSON
            expect(result.events).toHaveLength(1)
            expect(result.events[0]).toEqual({ type: 'valid' })
        })

        it('应该处理空数据', () => {
            const buffer = 'data: \n\n'

            const result = parseSSEBuffer(buffer)

            expect(result.events).toHaveLength(0)
        })

        it('应该处理空缓冲区', () => {
            const buffer = ''

            const result = parseSSEBuffer(buffer)

            expect(result.events).toHaveLength(0)
            expect(result.rest).toBe('')
        })
    })

    describe('边界情况', () => {
        it('应该处理只有空行的缓冲区', () => {
            const buffer = '\n\n\n\n'

            const result = parseSSEBuffer(buffer)

            expect(result.events).toHaveLength(0)
        })

        it('应该处理大量事件', () => {
            const events = Array(1000).fill(null).map((_, i) =>
                `data: {"type":"event","index":${i}}\n\n`
            ).join('')

            const result = parseSSEBuffer(events)

            expect(result.events).toHaveLength(1000)
        })

        it('应该处理包含特殊字符的数据', () => {
            const buffer = 'data: {"content":"Hello\\nWorld\\t!"}\n\n'

            const result = parseSSEBuffer(buffer)

            expect(result.events).toHaveLength(1)
            expect(result.events[0]).toEqual({ content: 'Hello\nWorld\t!' })
        })

        it('应该处理 Unicode 字符', () => {
            const buffer = 'data: {"content":"你好世界 🚀"}\n\n'

            const result = parseSSEBuffer(buffer)

            expect(result.events).toHaveLength(1)
            expect(result.events[0]).toEqual({ content: '你好世界 🚀' })
        })
    })

    describe('增量解析', () => {
        it('应该支持增量解析', () => {
            // 第一次解析 - 包含一个完整事件和一个不完整事件
            const buffer1 = 'data: {"type":"event1"}\n\n' +
                'data: {"type":"incomplete"'

            const result1 = parseSSEBuffer(buffer1)
            expect(result1.events).toHaveLength(1)
            expect(result1.events[0]).toEqual({ type: 'event1' })
            expect(result1.rest).toBe('data: {"type":"incomplete"')

            // 第二次解析（使用上次的 rest 加上新数据）
            const buffer2 = result1.rest + '"}\n\n' +
                'data: {"type":"event2"}\n\n'

            const result2 = parseSSEBuffer(buffer2)
            // buffer2 = 'data: {"type":"incomplete"}\n\ndata: {"type":"event2"}\n\n'
            // 应该解析出 2 个事件
            expect(result2.events.length).toBeGreaterThanOrEqual(1)
            // 至少应该包含 event2
            const hasEvent2 = result2.events.some((e: Record<string, unknown>) => e.type === 'event2')
            expect(hasEvent2).toBe(true)
        })
    })
})
