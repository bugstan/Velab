# Velab Web 前端测试文档

## 概述

本文档描述了 Velab 项目 Web 前端的完整测试套件，包括测试配置、运行方法、覆盖率要求和最佳实践。

## 测试技术栈

- **测试框架**: Vitest 4.1.2
- **组件测试**: React Testing Library 16.3.2
- **API 模拟**: MSW (Mock Service Worker) 2.12.14
- **用户交互**: @testing-library/user-event 14.6.1
- **覆盖率工具**: @vitest/coverage-v8 4.1.2
- **可视化界面**: @vitest/ui 4.1.2
- **类型支持**: TypeScript 6.0.2

## 项目结构

```
web/
├── vitest.config.ts            # Vitest 配置文件
├── vitest.setup.ts             # Vitest 设置文件
├── src/
│   ├── __tests__/              # 测试工具和 Mock
│   │   ├── mocks/
│   │   │   ├── data.ts         # 测试数据 Mock
│   │   │   ├── handlers.ts     # MSW 请求处理器
│   │   │   └── server.ts       # MSW 服务器配置
│   │   ├── utils/
│   │   │   └── test-utils.tsx  # 测试工具函数
│   │   └── setup.d.ts          # TypeScript 类型声明
│   ├── components/
│   │   └── __tests__/          # 组件测试
│   │       ├── ChatMessage.test.tsx
│   │       ├── ThinkingProcess.test.tsx
│   │       ├── InputBar.test.tsx
│   │       ├── Header.test.tsx
│   │       ├── WelcomePage.test.tsx
│   │       └── FeedbackButtons.test.tsx
│   ├── app/
│   │   ├── __tests__/
│   │   │   └── page.test.tsx   # 主页面集成测试
│   │   └── api/
│   │       └── chat/
│   │           └── __tests__/
│   │               └── route.test.ts  # API 路由测试
│   └── lib/
│       └── __tests__/
│           └── sseParse.test.ts       # SSE 解析器测试
```

## 测试命令

### 运行所有测试
```bash
npm test
```

### 监听模式（开发时使用）
```bash
npm run test:watch
```

### 生成覆盖率报告
```bash
npm run test:coverage
```

### 可视化测试界面
```bash
npm run test:ui
```

## 测试覆盖率

### 当前目标

- **分支覆盖率**: ≥ 70%
- **函数覆盖率**: ≥ 70%
- **行覆盖率**: ≥ 80%
- **语句覆盖率**: ≥ 80%

### 查看覆盖率报告

运行 `npm run test:coverage` 后，可以通过以下方式查看报告：

1. **终端输出**: 直接在终端查看汇总信息
2. **HTML 报告**: 打开 `coverage/lcov-report/index.html` 查看详细报告

## 测试分类

### 1. 组件测试

#### ChatMessage 组件
- ✅ 用户消息和助手消息渲染
- ✅ Markdown 解析（标题、列表、代码块、表格等）
- ✅ Thinking Process 展示
- ✅ 流式输出动画
- ✅ 反馈按钮显示逻辑

#### ThinkingProcess 组件
- ✅ 展开/折叠交互
- ✅ Agent 步骤状态显示（pending、running、completed）
- ✅ 状态图标渲染
- ✅ 当前步骤高亮

#### InputBar 组件
- ✅ 文本输入和提交
- ✅ Run/Stop 按钮切换
- ✅ 输入验证（空消息、空格）
- ✅ 键盘交互（Enter 提交）
- ✅ 按钮状态管理

#### Header 组件
- ✅ 场景下拉菜单
- ✅ 场景切换功能
- ✅ 点击外部关闭菜单
- ✅ 当前场景高亮

#### WelcomePage 组件
- ✅ 预设问题渲染
- ✅ 问题点击交互
- ✅ 响应式布局

#### FeedbackButtons 组件
- ✅ 复制功能和状态
- ✅ 点赞/点踩互斥逻辑
- ✅ 按钮状态切换

### 2. 集成测试

#### 主页面 (page.tsx)
- ✅ 完整的消息发送流程
- ✅ SSE 流式数据处理
- ✅ 场景切换和消息清空
- ✅ Stop 功能
- ✅ 错误处理
- ✅ 自动滚动

### 3. API 测试

#### /api/chat 路由
- ✅ 请求转发到后端
- ✅ SSE 流式响应
- ✅ 错误处理（网络错误、超时、后端错误）
- ✅ 请求体验证

### 4. 工具函数测试

#### SSE 解析器 (sseParse.ts)
- ✅ 单个和多个事件解析
- ✅ 不完整事件处理
- ✅ 多种行结束符支持
- ✅ 注释过滤
- ✅ 增量解析

## 测试最佳实践

### 1. AAA 模式

所有测试遵循 **Arrange-Act-Assert** 模式：

```typescript
it('应该正确渲染用户消息', () => {
  // Arrange - 准备测试数据
  const message = { role: 'user', content: 'Test' }
  
  // Act - 执行操作
  render(<ChatMessage message={message} />)
  
  // Assert - 验证结果
  expect(screen.getByText('Test')).toBeInTheDocument()
})
```

### 2. 测试隔离

每个测试应该独立运行，不依赖其他测试：

```typescript
beforeEach(() => {
  jest.clearAllMocks()
})
```

### 3. 用户视角测试

优先使用用户可见的元素进行查询：

```typescript
// ✅ 好的做法
screen.getByRole('button', { name: 'Submit' })
screen.getByText('Welcome')
screen.getByPlaceholderText('Enter text')

// ❌ 避免使用
container.querySelector('.submit-button')
```

### 4. 异步操作

使用 `waitFor` 处理异步更新：

```typescript
await waitFor(() => {
  expect(screen.getByText('Loaded')).toBeInTheDocument()
})
```

### 5. 用户交互

使用 `userEvent` 模拟真实用户操作：

```typescript
const user = userEvent.setup()
await user.type(input, 'Hello')
await user.click(button)
```

## Mock 策略

### 1. API Mock (MSW)

使用 MSW 模拟后端 API：

```typescript
// handlers.ts
export const handlers = [
  http.post('/api/chat', async ({ request }) => {
    return createSSEResponse(mockEvents)
  }),
]
```

### 2. 组件 Mock

对于复杂的子组件，可以使用 Jest mock：

```typescript
jest.mock('@/components/ComplexComponent', () => ({
  __esModule: true,
  default: () => <div>Mocked Component</div>,
}))
```

### 3. 环境变量

在 [`vitest.setup.ts`](vitest.setup.ts:1) 中配置测试环境变量：

```typescript
process.env.NEXT_PUBLIC_BACKEND_URL = 'http://localhost:8000'
```

## 常见问题

### 1. 测试超时

如果测试超时，增加超时时间：

```typescript
it('长时间运行的测试', async () => {
  // 测试代码
}, 10000) // 10 秒超时
```

### 2. 异步状态更新

使用 `waitFor` 等待状态更新：

```typescript
await waitFor(() => {
  expect(screen.getByText('Updated')).toBeInTheDocument()
})
```

### 3. 清理定时器

测试中使用定时器时，记得清理：

```typescript
jest.useFakeTimers()
// 测试代码
jest.advanceTimersByTime(2000)
jest.useRealTimers()
```

### 4. TypeScript 类型错误

确保导入了类型声明：

```typescript
import '@testing-library/jest-dom'
```

## 持续集成

### GitHub Actions 配置示例

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '20'
      - run: npm ci
      - run: npm run test:ci
      - uses: codecov/codecov-action@v3
        with:
          files: ./coverage/lcov.info
```

## 调试技巧

### 1. 查看渲染结果

```typescript
const { debug } = render(<Component />)
debug() // 打印当前 DOM 结构
```

### 2. 查询失败时的建议

```typescript
screen.getByRole('button') // 失败时会显示所有可用的 role
```

### 3. 测试特定场景

```bash
npm test -- --testNamePattern="应该正确渲染"
```

### 4. 更新快照

```bash
npm test -- -u
```

## 性能优化

### 1. 并行运行

Jest 默认并行运行测试，可以通过 `--maxWorkers` 调整：

```bash
npm test -- --maxWorkers=4
```

### 2. 只运行变更的测试

```bash
npm test -- --onlyChanged
```

### 3. 缓存

Jest 会自动缓存测试结果，加速后续运行。

## 贡献指南

### 添加新测试

1. 在相应目录创建 `*.test.tsx` 或 `*.test.ts` 文件
2. 遵循现有的测试结构和命名规范
3. 确保测试覆盖率不降低
4. 运行 `npm test` 确保所有测试通过

### 测试命名规范

- 使用中文描述测试场景
- 使用 `应该...` 开头描述预期行为
- 分组相关测试使用 `describe`

```typescript
describe('组件名称', () => {
  describe('功能分类', () => {
    it('应该执行某个操作', () => {
      // 测试代码
    })
  })
})
```

## 参考资源

- [Vitest 官方文档](https://vitest.dev/)
- [React Testing Library 文档](https://testing-library.com/react)
- [MSW 文档](https://mswjs.io/)
- [Testing Library 最佳实践](https://kentcdodds.com/blog/common-mistakes-with-react-testing-library)

## 更新日志

### 2026-04-03
- ✅ 初始化测试套件
- ✅ 配置 Jest 和 React Testing Library
- ✅ 添加所有组件测试
- ✅ 添加集成测试和 API 测试
- ✅ 配置 MSW 用于 API 模拟
- ✅ 设置测试覆盖率目标

---

**维护者**: FOTA 诊断平台团队  
**最后更新**: 2026-04-03
