/**
 * /api/upload-log POST 路由测试
 */
import { POST } from '@/app/api/upload-log/route'
import { NextRequest } from 'next/server'
import { vi, beforeEach, afterEach, describe, it, expect } from 'vitest'

describe('POST /api/upload-log', () => {
  let mockFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockFetch = vi.fn()
    vi.stubGlobal('fetch', mockFetch)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('转发 multipart 表单数据到后端', async () => {
    mockFetch.mockResolvedValue({
      status: 202,
      text: async () => '{"bundle_id":"b1","status":"queued"}',
    })
    // 直接 mock formData() 避免 undici File 与 JSDOM FormData 不兼容问题
    const mockFile = new File(['log content'], 'test.log', { type: 'text/plain' })
    const req = {
      formData: async () => {
        const fd = new FormData()
        fd.append('file', mockFile)
        return fd
      },
    } as unknown as import('next/server').NextRequest
    const res = await POST(req)
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/bundles'),
      expect.objectContaining({ method: 'POST' })
    )
    expect(res.status).toBe(202)
  })

  it('无文件时仍转发（空 FormData）', async () => {
    mockFetch.mockResolvedValue({ status: 400, text: async () => '{"error":"no file"}' })
    const formData = new FormData()
    const req = new NextRequest('http://localhost/api/upload-log', {
      method: 'POST',
      body: formData,
    })
    const res = await POST(req)
    expect(res.status).toBe(400)
  })
})
