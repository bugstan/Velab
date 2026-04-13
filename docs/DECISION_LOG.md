# Decision Log

项目重要架构决策和变更的历史记录。

---

### 2026-04-10: 部署脚本与 env 模板加固
- **config.py**: 新增 `REDIS_PASSWORD` 字段；`LITELLM_API_KEY` 默认值与 `.env.example` 对齐（`sk-fota-virtual-key`）
- **backend/.env.example**: 补全所有字段的 `config.py` 注解；清理 section 10 中已过时的 `DATABASE_URL`/`REDIS_URL` 注释行
- **gateway/.env.example**: 修正 section 1 注释（`synthesizer-model` 使用 `ANTHROPIC_API_KEY_1` 而非 `ANTHROPIC_API_KEY`）；新增 section 8 文档化 `GATEWAY_LOG_PATH`
- **gateway/systemd/litellm.service**: `--host`/`--port` 改为读取 `${HOST:-127.0.0.1}`/`${PORT:-4000}`，与 `.env` 联动
- **backend/scripts/check_env.sh**: 修复三处 Bug：① `CRITICAL_PACKAGES` 改为 `pip包名:模块名` 格式（`psycopg2-binary:psycopg2`、`python-dotenv:dotenv`）；② `set -e` + heredoc + `$?` 失效问题改为 `if python3 << EOF ... then/else` 模式；③ `REQUIRED_VARS`/`OPTIONAL_VARS` 变量名与实际 env 对齐
- **backend/scripts/deploy.sh**: Step 6 新增强随机 `POSTGRES_PASSWORD` 自动生成（检测弱密码 `fota_password` 时替换）；Step 7 加注 `create_all()` 不执行迁移的升级警告；Step 8 systemd restart 后执行 `is-active` 验证
- **gateway/scripts/deploy.sh**: Step 5 venv 检查改为检测 `venv/bin/pip` 是否存在（原仅检查目录，不完整时跳过重建导致失败）；Step 7 systemd restart 后执行 `is-active` 验证
- **web/scripts/deploy.sh**: Step 7 systemd restart 后执行 `is-active` 验证
- **scripts/deploy-all.sh**: 新增 `--mode`/`--domain` 命令行参数支持非交互式执行（CI/CD 友好）；Step 5 对账阶段新增 LLM API Key 占位值检测（场景 A/B 分别检测）和 `POSTGRES_PASSWORD` 弱密码检测
- **升级行为澄清**: 二次部署时 `.env` 受 `rsync --exclude` 保护、`POSTGRES_PASSWORD` 因值已非弱密码跳过生成、`create_all()` 幂等但不迁移列变更

### 2026-04-06: Sprint 4 批量实现
- 迁移 `main.py` 从废弃的 `@app.on_event` 到 `lifespan` context manager
- 创建 `vector_search.py` — 使用 TF-IDF baseline（不需要 API Key），预留 embedding 接口
- 创建 `doc_retrieval.py` — 第 3 个 Agent，加入 SCENARIO_AGENT_MAP
- 实现 3 个 Tool Use 函数（`extract_timeline_events`, `fetch_raw_line_context`, `search_fota_stage_transitions`）
- RCA Synthesizer 增加 `_validate_citations()` 引用 ID 断言验证
- 创建 `semantic_cache.py` 的 SHA-256 精确匹配模式
- 创建 `api/feedback.py`（5 个端点）和 `api/metrics.py`（Prometheus 格式）
- 创建 `evaluation.py` 评测框架（5 个标准 case，5 维评分）
- 创建 `doc_chunker.py` 支持 PDF/文本切块（3 种策略）
- 演示日志扩充至 5 份，Jira 工单扩充至 10 个
- `vitest.config.ts` 添加覆盖率 thresholds（branches≥70%, functions≥70%, lines≥80%, statements≥80%）
- 总体进度 80% → 93%
