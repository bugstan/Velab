---
name: velab-frontend-expert
description: Next.js 16 (App Router) 与 React 19 前端架构专家，精通 Tailwind CSS 4 及 FOTA 诊断平台的流式交互（SSE）和组件规范。
---

# Velab 前端专家开发指南

当监测到需要在 `web/` 目录下开发、修复或优化 Next.js 交互组件时，必须激活本辅助指南。

## 1. 核心架构与运行规范
- **技术栈**：Next.js 16 (App Router架构) + React 19 + Tailwind CSS 4 + TypeScript 6。
- **启动与验证**：开发启动命令为 `npm run dev`，端口 3000。所有新引入组件必须验证与 SSR/CSR (服务端渲染/客户端渲染) 的兼容性。使用 `"use client";` 仅在组件确实需要交互或浏览器 API 时。

## 2. Server-Sent Events (SSE) 处理规范
Velab 平台极度依赖流式响应（如日志分析过程、Agent 编排状态）。
- 解析流数据时需处理 `\n\n` 的切分容错。
- **UI 更新频率**：需在 SSE 处理流中对状态合并做平滑处理，避免 React 树的过度重绘。
- 在 `page.tsx` 或底层 provider 中维护好清理逻辑 `eventSource.close()`。

## 3. UI/UX 与关键组件
根据 Velab 的设计，使用以下原子组件和原则：
- **`ThinkingProcess` 组件**：用于折叠展示 Agent 工作编排和步骤演进状态。修改此组件时，请务必保证对异常状态 `Analyzing... -> Done / Failed` 的正确高亮。
- **`ChatMessage` 组件**：必须支持 Markdown 渲染（包含表格和置信度高亮）。对于特殊的内部模型标记（如 `<<<THINKING>>>`）执行特定的灰色折叠层样式截断。
- **`SourcePanel` 组件**：用来快速查看追溯来源。
- **样式**：严禁写行内 CSS，所有交互动画（如悬停、微动效）只能使用 Tailwind 工具类（例如 `hover:bg-slate-100 transition-colors` ）。

## 4. 类型安全
- 全局类型定义通常在 `src/lib/types.ts`。所有传入新组件的 Props 必须有明晰的 TypeScript interface。
- 绝不使用 `any`，对于不确定的动态 payload，使用 `unknown` 并配合 Type Guard。

## 5. 常规除错指引
- 遇到 `Module not found: Can't resolve 'react'` -> `rm -rf node_modules package-lock.json && npm install`。
- 遇到 Hydration Mismatch -> 检查是否在服务器端渲染了随机数或者依赖 `window` 对象的逻辑。
