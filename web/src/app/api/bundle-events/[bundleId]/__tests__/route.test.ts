/**
 * /api/bundle-events/[bundleId] GET 路由测试
 */
import { GET } from '@/app/api/bundle-events/[bundleId]/route'
import { NextRequest } from 'next/server'
import { vi, beforeEach, afterEach, describe, it, expect } from 'vitest'

const makeParams = (bundleId: string) =>
  ({ params: Promise.resolve({ bundleId }) }) as { params: Promise<{ bundleId: string }> }

describe('GET /api/bundle-events/[bundleId]', () => {
  let mockFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockFetch = vi.fn()
    vi.stubGlobal('fetch', mockFetch)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('转发到 /api/bundles/{id}/events', async () => {
    mockFetch.mockResolvedValue({ status: 200, text: async () => '[]' })
    const req = new NextRequest('http://localhost/api/bundle-events/b1')
    const res = await GET(req, makeParams('b1'))
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/bundles/b1/events'),
      expect.objectContaining({ method: 'GET' })
    )
    expect(res.status).toBe(200)
  })

  it('透传查询参数到上游', async () => {
    mockFetch.mockResolvedValue({ status: 200, text: async () => '[]' })
    const req = new NextRequest('http://localhost/api/bundle-events/b1?type=fota&limit=10')
    await GET(req, makeParams('b1'))
    const calledUrl: string = mockFetch.mock.calls[0][0]
    expect(calledUrl).toContain('type=fota')
    expect(calledUrl).toContain('limit=10')
  })
})
