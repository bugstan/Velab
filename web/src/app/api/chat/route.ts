/**
 * FOTA 诊断平台 — Next.js API 路由（聊天代理）
 *
 * 本模块作为前端和后端之间的代理层，负责：
 * 1. 接收前端的聊天请求
 * 2. 转发到 FastAPI 后端服务
 * 3. 流式透传 SSE 响应到前端
 * 4. 处理超时和错误情况
 *
 * 设计原因：
 * - Next.js 的 API Routes 可以处理服务端逻辑
 * - 避免前端直接暴露后端 URL
 * - 统一处理 CORS 和错误
 *
 * @author FOTA 诊断平台团队
 * @created 2025
 * @updated 2025
 */

import { NextRequest } from "next/server";

// 后端服务地址，优先使用环境变量配置
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

// Vercel 函数最大执行时间（秒）
export const maxDuration = 120;

/**
 * 处理聊天请求的 POST 端点
 *
 * 接收前端的聊天消息，转发到后端 FastAPI 服务，并流式透传 SSE 响应。
 *
 * @param request - Next.js 请求对象
 * @returns SSE 流式响应或错误响应
 *
 * @example
 * // 前端调用示例
 * fetch('/api/chat', {
 *   method: 'POST',
 *   body: JSON.stringify({
 *     message: '用户问题',
 *     scenarioId: 'fota-diagnostic',
 *     history: []
 *   })
 * })
 */
export async function POST(request: NextRequest) {
  const body = await request.json();

  // 创建 AbortController 用于超时控制
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 120_000); // 120秒超时

  try {
    // 转发请求到后端服务
    const backendResponse = await fetch(`${BACKEND_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    // 检查后端响应状态
    if (!backendResponse.ok) {
      return new Response(JSON.stringify({ error: "Backend error" }), {
        status: backendResponse.status,
      });
    }

    // 获取响应流
    const stream = backendResponse.body;
    if (!stream) {
      return new Response(JSON.stringify({ error: "No response body" }), {
        status: 502,
      });
    }

    // 透传 SSE 流到前端
    return new Response(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  } catch (err) {
    clearTimeout(timeoutId);
    const message = err instanceof Error ? err.message : "Unknown error";
    return new Response(JSON.stringify({ error: message }), { status: 504 });
  }
}
