/**
 * /api/session-title POST 路由测试
 */
import { POST } from '@/app/api/session-title/route'
import { NextRequest } from 'next/server'
import { vi, beforeEach, afterEach, describe, it, expect } from 'vitest'

describe('POST /api/session-title', () => {
  let mockFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockFetch = vi.fn()
    vi.stubGlobal('fetch', mockFetch)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('转发请求体到后端并返回标题', async () => {
    mockFetch.mockResolvedValue({ status: 200, text: async () => '{"title":"FOTA升级诊断"}' })
    const req = new NextRequest('http://localhost/api/session-title', {
      method: 'POST',
      body: JSON.stringify({ messages: [] }),
    })
    const res = await POST(req)
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/sessions/title'),
      expect.objectContaining({ method: 'POST', headers: { 'Content-Type': 'application/json' } })
    )
    expect(res.status).toBe(200)
  })

  it('透传后端 500 错误', async () => {
    mockFetch.mockResolvedValue({ status: 500, text: async () => 'error' })
    const req = new NextRequest('http://localhost/api/session-title', {
      method: 'POST',
      body: '{}',
    })
    const res = await POST(req)
    expect(res.status).toBe(500)
  })
})
