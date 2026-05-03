# Velab FOTA 诊断平台 — Copilot 编码规范

项目概述：基于 AI 的车辆固件升级（FOTA）诊断系统，多 Agent 协作架构。
后端：Python 3.12 + FastAPI（异步）；前端：Next.js 16 + React 19 + TypeScript。

---

## 测试（强制）

- 每次修改后运行测试：后端 `pytest`，前端 `npm test`
- Bug 修复必须先写失败测试，再修代码（Prove-It 模式）
- 不得删除或注释掉已有测试
- 前端覆盖率红线：branches ≥ 70%，functions ≥ 70%，lines ≥ 80%，statements ≥ 80%

## 代码质量（强制）

- 每个变更控制在 ~100 行以内（分批提交）
- 禁止格式变更与逻辑变更混入同一次提交
- 禁止未使用的变量、死代码、魔法字符串
- TypeScript：强制类型，禁止无故使用 `any`

## 实现规范

- 小步验证：实现 → 测试 → 确认 → 提交，循环递进
- 新增 Agent 必须继承 `BaseAgent` 并调用 `registry.register()`
- 所有后端异步方法以 `async` 修饰，方法签名支持 `trace_id`
- 敏感字段（VIN 码、手机号）必须经 `redactor` 脱敏后才能输出

## 安全（零容忍）

- 严禁将 API Key、密码、Token 提交到版本库
- 严禁在日志中输出密码、Token、完整信用卡号
- 所有用户输入必须在 API 边界处验证（FastAPI 使用 Pydantic，前端使用 Zod）
- SQL 查询必须参数化，禁止拼接用户输入
- API 响应禁止暴露堆栈信息或内部错误细节

## 边界约定

| 始终执行 | 需确认后执行 | 绝对不做 |
|----------|-------------|----------|
| 运行测试再提交 | 数据库 Schema 变更 | 提交 secrets |
| 验证用户输入 | 新增外部依赖 | 删除失败测试 |
| 参数化 SQL 查询 | 修改 CORS 配置 | 跳过验证步骤 |
| 脱敏敏感字段 | 修改认证逻辑 | 禁用安全 Header |

## Git 提交规范

遵循 Conventional Commits：`feat:` / `fix:` / `docs:` / `test:` / `refactor:`。
