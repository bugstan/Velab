/**
 * /api/sessions GET 路由测试
 */
import { GET } from '@/app/api/sessions/route'
import { vi, beforeEach, afterEach, describe, it, expect } from 'vitest'

describe('GET /api/sessions', () => {
  let mockFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockFetch = vi.fn()
    vi.stubGlobal('fetch', mockFetch)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('转发到后端并返回响应体', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => '[{"id":"s1"}]',
    })
    const res = await GET()
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/sessions'),
      expect.objectContaining({ method: 'GET' })
    )
    expect(res.status).toBe(200)
    expect(await res.text()).toBe('[{"id":"s1"}]')
  })

  it('透传后端错误状态码', async () => {
    mockFetch.mockResolvedValue({ ok: false, status: 503, text: async () => '' })
    const res = await GET()
    expect(res.status).toBe(503)
  })
})
