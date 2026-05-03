/**
 * /api/bundle-logs/[bundleId] GET 路由测试
 */
import { GET } from '@/app/api/bundle-logs/[bundleId]/route'
import { NextRequest } from 'next/server'
import { vi, beforeEach, afterEach, describe, it, expect } from 'vitest'

const makeParams = (bundleId: string) =>
  ({ params: Promise.resolve({ bundleId }) }) as { params: Promise<{ bundleId: string }> }

describe('GET /api/bundle-logs/[bundleId]', () => {
  let mockFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockFetch = vi.fn()
    vi.stubGlobal('fetch', mockFetch)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('转发到 /api/bundles/{id}/logs', async () => {
    mockFetch.mockResolvedValue({
      status: 200,
      headers: { get: (_: string) => null },
      text: async () => 'line1\nline2',
    })
    const req = new NextRequest('http://localhost/api/bundle-logs/b1')
    const res = await GET(req, makeParams('b1'))
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/bundles/b1/logs'),
      expect.objectContaining({ method: 'GET' })
    )
    expect(res.status).toBe(200)
  })

  it('透传 X-Truncated 和 X-Estimated-Lines 响应头', async () => {
    mockFetch.mockResolvedValue({
      status: 200,
      headers: {
        get: (name: string) => {
          if (name === 'x-truncated') return 'true'
          if (name === 'x-estimated-lines') return '1000'
          if (name === 'content-type') return 'application/x-ndjson'
          return null
        },
      },
      text: async () => '',
    })
    const req = new NextRequest('http://localhost/api/bundle-logs/b1')
    const res = await GET(req, makeParams('b1'))
    expect(res.headers.get('X-Truncated')).toBe('true')
    expect(res.headers.get('X-Estimated-Lines')).toBe('1000')
  })

  it('查询参数透传到上游', async () => {
    mockFetch.mockResolvedValue({
      status: 200,
      headers: { get: () => null },
      text: async () => '',
    })
    const req = new NextRequest('http://localhost/api/bundle-logs/b1?controller=iCGM&limit=50')
    await GET(req, makeParams('b1'))
    const calledUrl: string = mockFetch.mock.calls[0][0]
    expect(calledUrl).toContain('controller=iCGM')
    expect(calledUrl).toContain('limit=50')
  })
})
