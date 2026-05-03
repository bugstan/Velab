/**
 * /api/bundle-status/[bundleId] GET 路由测试
 */
import { GET } from '@/app/api/bundle-status/[bundleId]/route'
import { NextRequest } from 'next/server'
import { vi, beforeEach, afterEach, describe, it, expect } from 'vitest'

const makeParams = (bundleId: string) =>
  ({ params: Promise.resolve({ bundleId }) }) as { params: Promise<{ bundleId: string }> }

describe('GET /api/bundle-status/[bundleId]', () => {
  let mockFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockFetch = vi.fn()
    vi.stubGlobal('fetch', mockFetch)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('转发请求到后端并返回 bundle 状态', async () => {
    mockFetch.mockResolvedValue({
      status: 200,
      text: async () => '{"id":"b1","status":"done"}',
    })
    const req = new NextRequest('http://localhost/api/bundle-status/b1')
    const res = await GET(req, makeParams('b1'))
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/bundles/b1'),
      expect.objectContaining({ method: 'GET' })
    )
    expect(res.status).toBe(200)
  })

  it('透传 404 状态码', async () => {
    mockFetch.mockResolvedValue({ status: 404, text: async () => '{"detail":"not found"}' })
    const req = new NextRequest('http://localhost/api/bundle-status/missing')
    const res = await GET(req, makeParams('missing'))
    expect(res.status).toBe(404)
  })
})
