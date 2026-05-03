/**
 * /api/sessions/[sessionId] GET/PUT/DELETE 路由测试
 */
import { GET, PUT, DELETE } from '@/app/api/sessions/[sessionId]/route'
import { NextRequest } from 'next/server'
import { vi, beforeEach, afterEach, describe, it, expect } from 'vitest'

const makeParams = (sessionId: string) =>
  ({ params: Promise.resolve({ sessionId }) }) as { params: Promise<{ sessionId: string }> }

describe('/api/sessions/[sessionId]', () => {
  let mockFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockFetch = vi.fn()
    vi.stubGlobal('fetch', mockFetch)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  describe('GET', () => {
    it('转发 GET 请求到后端', async () => {
      mockFetch.mockResolvedValue({ status: 200, text: async () => '{"id":"abc"}' })
      const req = new NextRequest('http://localhost/api/sessions/abc')
      const res = await GET(req, makeParams('abc'))
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/sessions/abc'),
        expect.objectContaining({ method: 'GET' })
      )
      expect(res.status).toBe(200)
    })
  })

  describe('PUT', () => {
    it('转发 PUT 请求并附带请求体', async () => {
      mockFetch.mockResolvedValue({ status: 200, text: async () => '{"updated":true}' })
      const req = new NextRequest('http://localhost/api/sessions/abc', {
        method: 'PUT',
        body: JSON.stringify({ title: 'New Title' }),
      })
      const res = await PUT(req, makeParams('abc'))
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/sessions/abc'),
        expect.objectContaining({ method: 'PUT' })
      )
      expect(res.status).toBe(200)
    })
  })

  describe('DELETE', () => {
    it('转发 DELETE 请求并返回 204', async () => {
      mockFetch.mockResolvedValue({ status: 204 })
      const req = new NextRequest('http://localhost/api/sessions/abc', { method: 'DELETE' })
      const res = await DELETE(req, makeParams('abc'))
      expect(res.status).toBe(204)
    })
  })
})
